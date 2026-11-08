"""Turn settled weeks into the public report the website reads (web/public/data/report.json).

Money rules (v1): £20 on the aker each week; a week counts towards money (and 'who sank it') only
when all four legs are known and settled - a week missing a leg would look like a shorter acca. 'Singles' shows what each person would have made staking £5 on their own leg instead.
"""
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from scipy.stats import fisher_exact

from aker.config import PEOPLE
from aker.models import Outcome, SettledLeg, SettledWeek

STAKE = 20.0
SINGLE_STAKE = 5.0


@dataclass(frozen=True)
class LegView:
    person: str
    team: str
    opponent: str | None
    home: bool | None
    league: str | None
    bets: str
    selection_text: str
    outcome: str
    score: str | None  # from the picked team's side, e.g. "2-1"
    odds: float | None
    odds_estimated: bool
    probability: float | None


@dataclass(frozen=True)
class WeekView:
    matchday: date
    placer: str
    legs: list[LegView]
    complete: bool
    won: bool
    odds: float | None
    returned: float | None


@dataclass(frozen=True)
class PersonStats:
    person: str
    legs: int
    settled: int
    won: int
    hit_rate: float | None
    expected_wins: float  # sum of bookies' probabilities for priced, settled legs
    luck: float  # won − expected_wins, over priced legs only
    average_odds: float | None
    sole_loser: int  # weeks lost on this person's leg alone
    singles_profit: float  # £5 on each of their own legs
    scottish_legs: int


@dataclass(frozen=True)
class ScottishQuestion:
    peter_share: float
    others_share: float
    odds_ratio: float | None
    p_value: float  # Fisher's exact test, Peter vs the other three
    verdict: str


@dataclass(frozen=True)
class Summary:
    weeks: int
    weeks_settled: int
    weeks_won: int
    staked: float
    returned: float
    profit: float
    biggest_win: WeekView | None


@dataclass(frozen=True)
class Report:
    generated_at: datetime
    people: list[str]
    summary: Summary
    leaderboard: list[PersonStats]
    scottish: ScottishQuestion
    weeks: list[WeekView]


def _leg_view(leg: SettledLeg) -> LegView:
    f, p = leg.fixture, leg.pick
    home = f.home == p.team if f else None
    return LegView(
        person=p.person,
        team=p.team,
        opponent=(f.away if home else f.home) if f else None,
        home=home,
        league=f.league if f else None,
        bets="+".join(map(str, p.bets)),
        selection_text=p.selection_text,
        outcome=leg.outcome.value,
        score=(f"{f.home_goals}-{f.away_goals}" if home else f"{f.away_goals}-{f.home_goals}") if f else None,
        odds=round(leg.odds, 3) if leg.odds else None,
        odds_estimated=leg.odds_estimated,
        probability=round(leg.probability, 4) if leg.probability is not None else None,
    )


def _week_view(week: SettledWeek) -> WeekView:
    odds = week.odds
    returned = (STAKE * odds if week.won else 0.0) if week.complete and odds else None
    return WeekView(
        matchday=week.matchday,
        placer=week.placer,
        legs=[_leg_view(l) for l in week.legs],
        complete=week.complete,
        won=week.won,
        odds=round(odds, 2) if odds else None,
        returned=round(returned, 2) if returned is not None else None,
    )


def _is_scottish(leg: SettledLeg) -> bool:
    return bool(leg.fixture and leg.fixture.league.startswith("SC"))


def _person_stats(person: str, weeks: Sequence[SettledWeek]) -> PersonStats:
    legs = [l for w in weeks for l in w.legs if l.pick.person == person]
    settled = [l for l in legs if l.outcome is not Outcome.UNSETTLED]
    won = [l for l in settled if l.outcome is Outcome.WON]
    priced = [l for l in settled if l.probability is not None]
    expected = sum(l.probability for l in priced)
    priced_wins = sum(l.outcome is Outcome.WON for l in priced)
    singles = sum(
        SINGLE_STAKE * (l.odds - 1) if l.outcome is Outcome.WON else -SINGLE_STAKE
        for l in settled if l.odds
    )
    sole = sum(
        1 for w in weeks if w.complete and not w.won
        and [l.pick.person for l in w.legs if l.outcome is Outcome.LOST] == [person]
    )
    odds = [l.odds for l in priced if l.odds]
    return PersonStats(
        person=person,
        legs=len(legs),
        settled=len(settled),
        won=len(won),
        hit_rate=round(len(won) / len(settled), 4) if settled else None,
        expected_wins=round(expected, 2),
        luck=round(priced_wins - expected, 2),
        average_odds=round(sum(odds) / len(odds), 2) if odds else None,
        sole_loser=sole,
        singles_profit=round(singles, 2),
        scottish_legs=sum(_is_scottish(l) for l in legs),
    )


def _scottish_question(weeks: Sequence[SettledWeek]) -> ScottishQuestion:
    with_fixture = [l for w in weeks for l in w.legs if l.fixture]
    peter = [l for l in with_fixture if l.pick.person == "Peter"]
    others = [l for l in with_fixture if l.pick.person != "Peter"]
    ps, os_ = sum(map(_is_scottish, peter)), sum(map(_is_scottish, others))
    table = [[ps, len(peter) - ps], [os_, len(others) - os_]]
    odds_ratio, p_value = fisher_exact(table, alternative="greater")
    peter_share, others_share = ps / len(peter), os_ / len(others)
    if p_value < 0.05:
        verdict = f"Yes. Peter picks Scottish teams {peter_share:.0%} of the time vs {others_share:.0%} for the rest."
    else:
        verdict = f"Not proven: {peter_share:.0%} vs {others_share:.0%} could be chance."
    return ScottishQuestion(
        peter_share=round(peter_share, 4),
        others_share=round(others_share, 4),
        odds_ratio=None if odds_ratio == float("inf") else round(float(odds_ratio), 2),
        p_value=round(float(p_value), 5),
        verdict=verdict,
    )


def build(weeks: Sequence[SettledWeek]) -> Report:
    views = [_week_view(w) for w in weeks]
    settled = [v for v in views if v.returned is not None]
    returned = sum(v.returned for v in settled)
    won = [v for v in settled if v.won]
    return Report(
        generated_at=datetime.now().replace(microsecond=0),
        people=list(PEOPLE),
        summary=Summary(
            weeks=len(views),
            weeks_settled=len(settled),
            weeks_won=len(won),
            staked=STAKE * len(settled),
            returned=round(returned, 2),
            profit=round(returned - STAKE * len(settled), 2),
            biggest_win=max(won, key=lambda v: v.returned, default=None),
        ),
        leaderboard=sorted(
            (_person_stats(p, weeks) for p in PEOPLE), key=lambda s: s.hit_rate or 0, reverse=True
        ),
        scottish=_scottish_question(weeks),
        weeks=views,
    )


def write(report: Report, path: Path) -> None:
    path.write_text(json.dumps(asdict(report), default=str, indent=1))
