"""Assemble the final picks: referee answer where a week was refereed, else the extractor's,
with human labels on top. Also lists what needs a human: doubtful picks and missing ones."""
import csv
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path

from aker.config import PEOPLE
from aker.models import (
    NO_TEAM, Bet, ConditionType, FinalPick, Label, Market, PickSource, RefereedWeek, ReviewItem, SlipRead, Week,
)

# Claude's first-pass market → bets (only used for weeks the referee didn't look at, which are all plain wins).
_MARKET_BETS = {Market.WIN: (Bet(ConditionType.WIN),)}
LABEL_FIELDS = ["matchday", "person", "team", "bets"]


def _from_referee(matchday: date, week: RefereedWeek) -> list[FinalPick]:
    return [
        FinalPick(
            matchday=matchday,
            person=s.person,
            team=s.team,
            bets=tuple(Bet(c.type, c.line) for c in s.conditions),
            selection_text=s.selection_text,
            source=PickSource.REFEREE,
            confident=s.confident,
        )
        for s in week.selections
        if s.team != NO_TEAM
    ]


def _from_extract(matchday: date, week: Week) -> list[FinalPick]:
    return [
        FinalPick(
            matchday=matchday,
            person=p.person,
            team=p.team,
            bets=_MARKET_BETS.get(p.market, (Bet(ConditionType.OTHER),)),
            selection_text=p.selection_text,
            source=PickSource.EXTRACT,
            confident=p.confident,
        )
        for p in week.picks
        if p.team != NO_TEAM
    ]


def placers(claude: Mapping[date, Week], refereed: Mapping[date, RefereedWeek]) -> dict[date, str]:
    return {d: (refereed[d].placer if d in refereed else w.placer) for d, w in claude.items()}


def aker_matchdays(claude: Mapping[date, Week], refereed: Mapping[date, RefereedWeek]) -> list[date]:
    days = {d for d, w in claude.items() if w.aker_on and d not in refereed}
    days |= {d for d, w in refereed.items() if w.aker_on}
    return sorted(days)


def unaccounted_slip_legs(day: date, week_picks: Sequence[FinalPick], slips: Sequence[SlipRead]) -> list:
    """Legs on that week's (largest) bet slip that don't match any pick already known."""
    if not slips:
        return []
    slip = max(slips, key=lambda s: len(s.legs))
    known = {p.team for p in week_picks}
    return [leg for leg in slip.legs if leg.team != NO_TEAM and leg.team not in known]


def _fill_from_slip(day: date, week_picks: list[FinalPick], slips: Sequence[SlipRead]) -> list[FinalPick]:
    missing = [p for p in PEOPLE if p not in {wp.person for wp in week_picks}]
    legs = unaccounted_slip_legs(day, week_picks, slips)
    if len(missing) == 1 and len(legs) == 1:  # unambiguous: the only gap gets the only spare leg
        leg = legs[0]
        week_picks.append(FinalPick(
            matchday=day, person=missing[0], team=leg.team,
            bets=tuple(Bet(c.type, c.line) for c in leg.conditions) or (Bet(ConditionType.WIN),),
            selection_text="(from bet slip)", source=PickSource.SLIP, confident=True,
        ))
    return week_picks


def assemble(
    claude: Mapping[date, Week],
    refereed: Mapping[date, RefereedWeek],
    labels: Iterable[Label],
    slips: Mapping[date, Sequence[SlipRead]] | None = None,
) -> list[FinalPick]:
    picks: dict[tuple[date, str], FinalPick] = {}
    for day in aker_matchdays(claude, refereed):
        week_picks = _from_referee(day, refereed[day]) if day in refereed else _from_extract(day, claude[day])
        week_picks = _fill_from_slip(day, week_picks, (slips or {}).get(day, []))
        picks |= {(p.matchday, p.person): p for p in week_picks}
    for label in labels:  # human labels always win
        key = (label.matchday, label.person)
        if label.team is None:
            picks.pop(key, None)
        else:
            base = picks.get(key)
            picks[key] = FinalPick(
                matchday=label.matchday, person=label.person, team=label.team, bets=label.bets,
                selection_text=base.selection_text if base else "", source=PickSource.LABEL, confident=True,
            )
    return sorted(picks.values(), key=lambda p: (p.matchday, p.person))


def review_items(
    picks: Sequence[FinalPick],
    matchdays: Sequence[date],
    labels: Iterable[Label],
    slips: Mapping[date, Sequence[SlipRead]] | None = None,
) -> list[ReviewItem]:
    labelled = {(l.matchday, l.person) for l in labels}
    by_key = {(p.matchday, p.person): p for p in picks}
    items = []
    for day in matchdays:
        week_picks = [p for p in picks if p.matchday == day]
        hints = tuple(leg.team for leg in unaccounted_slip_legs(day, week_picks, (slips or {}).get(day, [])))
        for person in PEOPLE:
            if (day, person) in labelled:
                continue
            pick = by_key.get((day, person))
            if pick is None:
                items.append(ReviewItem(day, person, "missing", None, hints))
            elif any(b.type is ConditionType.OTHER for b in pick.bets):
                items.append(ReviewItem(day, person, "unsettleable", pick))
            elif not pick.confident:
                items.append(ReviewItem(day, person, "unsure", pick))
    return items


def read_labels(path: Path) -> list[Label]:
    if not path.exists():
        return []
    with path.open() as f:
        return [
            Label(
                matchday=date.fromisoformat(r["matchday"]),
                person=r["person"],
                team=r["team"] or None,
                bets=tuple(Bet.parse(b) for b in r["bets"].split(";") if b),
            )
            for r in csv.DictReader(f)
        ]


def write_labels(labels: Iterable[Label], path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(LABEL_FIELDS)
        for l in sorted(labels, key=lambda l: (l.matchday, l.person)):
            w.writerow([l.matchday.isoformat(), l.person, l.team or "", ";".join(map(str, l.bets))])


def with_no_fixture_flags(items: list[ReviewItem], unsettled: Iterable[FinalPick]) -> list[ReviewItem]:
    """Add picks whose fixture couldn't be found (wrong club, or not a Saturday game)."""
    seen = {(i.matchday, i.person) for i in items}
    extra = [ReviewItem(p.matchday, p.person, "no_fixture", p) for p in unsettled if (p.matchday, p.person) not in seen]
    return sorted([*items, *extra], key=lambda i: (i.matchday, i.person))

