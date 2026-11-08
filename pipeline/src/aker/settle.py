"""Settle each leg against the final score, and price it.

Win/draw/double-chance and over/under 2.5 use bookies' prices (Bet365, else market average).
Anything else (BTTS, other goal lines, combinations) is priced from a Poisson goals model fitted
to that match's 1X2 and over/under 2.5 prices, and flagged as estimated.
"""
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import cached_property

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from aker.models import Bet, ConditionType, FinalPick, Fixture, Outcome, SettledLeg, SettledWeek

MAX_GOALS = 10


def _num(value: object) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


def _odds(row: Mapping[str, object], primary: str, fallback: str | None = None) -> float | None:
    return _num(row.get(primary)) or (_num(row.get(fallback)) if fallback else None)


def fixtures_by_team(results: pd.DataFrame) -> dict[tuple[date, str], Fixture]:
    index: dict[tuple[date, str], Fixture] = {}
    for r in results.dropna(subset=["FTHG", "FTAG"]).to_dict("records"):
        fixture = Fixture(
            date=r["Date"].date(),
            league=r["League"],
            home=r["HomeTeam"],
            away=r["AwayTeam"],
            home_goals=int(r["FTHG"]),
            away_goals=int(r["FTAG"]),
            kickoff=None if pd.isna(r.get("Time")) else str(r["Time"]),
            odds_home=_odds(r, "B365H", "AvgH"),
            odds_draw=_odds(r, "B365D", "AvgD"),
            odds_away=_odds(r, "B365A", "AvgA"),
            odds_over25=_num(r.get("B365>2.5")),
            odds_under25=_num(r.get("B365<2.5")),
        )
        index[(fixture.date, fixture.home)] = fixture
        index[(fixture.date, fixture.away)] = fixture
    return index


# --- Outcomes ----------------------------------------------------------------------------------


def _bet_wins(bet: Bet, team_goals: int, opp_goals: int) -> bool | None:
    total = team_goals + opp_goals
    match bet.type:
        case ConditionType.WIN:
            return team_goals > opp_goals
        case ConditionType.DRAW:
            return team_goals == opp_goals
        case ConditionType.DOUBLE_CHANCE:
            return team_goals >= opp_goals
        case ConditionType.OVER_GOALS:
            return total > bet.line
        case ConditionType.UNDER_GOALS:
            return total < bet.line
        case ConditionType.BTTS:
            return team_goals > 0 and opp_goals > 0
        case ConditionType.BTTS_NO:
            return team_goals == 0 or opp_goals == 0
        case ConditionType.TEAM_OVER_GOALS:
            return team_goals > bet.line
        case _:
            return None


def _goals_for(pick: FinalPick, fixture: Fixture) -> tuple[int, int]:
    home = fixture.home == pick.team
    return (fixture.home_goals, fixture.away_goals) if home else (fixture.away_goals, fixture.home_goals)


# --- Pricing -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchPrices:
    """Bookies' prices for one fixture, from the picked team's point of view."""

    team: float | None
    draw: float | None
    opponent: float | None
    over25: float | None
    under25: float | None

    @classmethod
    def for_pick(cls, pick: FinalPick, fixture: Fixture) -> "MatchPrices":
        home = fixture.home == pick.team
        return cls(
            team=fixture.odds_home if home else fixture.odds_away,
            draw=fixture.odds_draw,
            opponent=fixture.odds_away if home else fixture.odds_home,
            over25=fixture.odds_over25,
            under25=fixture.odds_under25,
        )

    @property
    def has_1x2(self) -> bool:
        return None not in (self.team, self.draw, self.opponent)

    @cached_property
    def probabilities_1x2(self) -> tuple[float, float, float]:
        """Implied win/draw/lose probabilities with the bookie's margin removed."""
        raw = [1 / self.team, 1 / self.draw, 1 / self.opponent]
        total = sum(raw)
        return tuple(p / total for p in raw)

    @cached_property
    def probability_over25(self) -> float | None:
        if self.over25 is None or self.under25 is None:
            return None
        over, under = 1 / self.over25, 1 / self.under25
        return over / (over + under)


def _score_grid(team_rate: float, opp_rate: float) -> np.ndarray:
    goals = np.arange(MAX_GOALS + 1)
    team = np.exp(-team_rate) * team_rate ** goals / np.array([math.factorial(g) for g in goals])
    opp = np.exp(-opp_rate) * opp_rate ** goals / np.array([math.factorial(g) for g in goals])
    return np.outer(team, opp)  # [team_goals, opp_goals]


def _fit_goal_rates(prices: MatchPrices) -> tuple[float, float]:
    """Poisson goal rates (team, opponent) that best reproduce the bookies' probabilities."""
    target_1x2 = np.array(prices.probabilities_1x2)
    target_over = prices.probability_over25
    t, o = np.meshgrid(np.arange(MAX_GOALS + 1), np.arange(MAX_GOALS + 1), indexing="ij")

    def loss(rates: np.ndarray) -> float:
        grid = _score_grid(*np.clip(rates, 0.05, 6))
        model = np.array([grid[t > o].sum(), grid[t == o].sum(), grid[t < o].sum()])
        err = ((model - target_1x2) ** 2).sum()
        if target_over is not None:
            err += (grid[t + o > 2.5].sum() - target_over) ** 2
        return err

    fit = minimize(loss, x0=np.array([1.4, 1.1]), method="Nelder-Mead")
    return tuple(np.clip(fit.x, 0.05, 6))


def _model_probability(bets: Sequence[Bet], prices: MatchPrices) -> float:
    grid = _score_grid(*_fit_goal_rates(prices))
    total = 0.0
    for team_goals in range(MAX_GOALS + 1):
        for opp_goals in range(MAX_GOALS + 1):
            if all(_bet_wins(b, team_goals, opp_goals) for b in bets):
                total += grid[team_goals, opp_goals]
    return total


def _quoted(bet: Bet, prices: MatchPrices) -> tuple[float, float] | None:
    """(probability, odds) for a single bet with a quoted market, else None."""
    if not prices.has_1x2:
        return None
    p_win, p_draw, _ = prices.probabilities_1x2
    match bet.type:
        case ConditionType.WIN:
            return p_win, prices.team
        case ConditionType.DRAW:
            return p_draw, prices.draw
        case ConditionType.DOUBLE_CHANCE:
            return p_win + p_draw, 1 / (1 / prices.team + 1 / prices.draw)
        case ConditionType.OVER_GOALS if bet.line == 2.5 and prices.over25:
            return prices.probability_over25, prices.over25
        case ConditionType.UNDER_GOALS if bet.line == 2.5 and prices.under25:
            return 1 - prices.probability_over25, prices.under25
    return None


def price(pick: FinalPick, fixture: Fixture) -> tuple[float | None, float | None, bool]:
    """(probability, decimal odds, estimated?) for a leg."""
    prices = MatchPrices.for_pick(pick, fixture)
    if len(pick.bets) == 1 and (quoted := _quoted(pick.bets[0], prices)):
        return quoted[0], quoted[1], False
    if not prices.has_1x2 or any(b.type is ConditionType.OTHER for b in pick.bets):
        return None, None, False
    p = _model_probability(pick.bets, prices)
    return p, (1 / p if p > 0 else None), True


# --- Settlement --------------------------------------------------------------------------------


def settle_leg(pick: FinalPick, fixtures: Mapping[tuple[date, str], Fixture]) -> SettledLeg:
    fixture = fixtures.get((pick.matchday, pick.team))
    if fixture is None:
        return SettledLeg(pick, None, Outcome.UNSETTLED, None, None, False)
    team_goals, opp_goals = _goals_for(pick, fixture)
    results = [_bet_wins(b, team_goals, opp_goals) for b in pick.bets]
    if any(r is None for r in results):
        outcome = Outcome.UNSETTLED
    else:
        outcome = Outcome.WON if all(results) else Outcome.LOST
    probability, odds, estimated = price(pick, fixture)
    return SettledLeg(pick, fixture, outcome, probability, odds, estimated)


def settle(
    picks: Iterable[FinalPick], placers: Mapping[date, str], results: pd.DataFrame
) -> list[SettledWeek]:
    fixtures = fixtures_by_team(results)
    by_day: dict[date, list[SettledLeg]] = {}
    for pick in picks:
        by_day.setdefault(pick.matchday, []).append(settle_leg(pick, fixtures))
    return [
        SettledWeek(day, placers.get(day, "unknown"), tuple(sorted(legs, key=lambda l: l.pick.person)))
        for day, legs in sorted(by_day.items())
    ]
