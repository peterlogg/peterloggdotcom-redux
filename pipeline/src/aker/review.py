"""Compare the Claude and Jev extractions pick by pick.

One row per (Saturday, person) where either model found a pick:
  agree     same club, both confident → auto-accepted
  low_conf  same club, but Jev's confidence is low or Claude flagged it → quick check
  disagree  different clubs → needs refereeing
"""
import csv
from collections.abc import Mapping, Sequence
from dataclasses import asdict, fields
from datetime import date
from pathlib import Path

from aker.config import PEOPLE
from aker.models import NO_TEAM, JevPick, JevWeek, Pick, ReviewRow, ReviewStatus, Week

JEV_AKER_THRESHOLD = 0.5
JEV_PICKED_THRESHOLD = 0.5
JEV_CONFIDENCE_THRESHOLD = 0.6


def _jev_team(week: JevWeek | None, pick: JevPick | None) -> str:
    if week and pick and week.aker_on >= JEV_AKER_THRESHOLD and pick.picked >= JEV_PICKED_THRESHOLD:
        return pick.team
    return NO_TEAM


def _status(claude_team: str, jev_team: str, claude: Pick | None, jev: JevPick | None) -> ReviewStatus:
    if claude_team != jev_team:
        return ReviewStatus.DISAGREE
    if (jev and jev.team_confidence < JEV_CONFIDENCE_THRESHOLD) or (claude and not claude.confident):
        return ReviewStatus.LOW_CONFIDENCE
    return ReviewStatus.AGREE


def _rows_for_week(matchday: date, claude_week: Week | None, jev_week: JevWeek | None) -> list[ReviewRow]:
    claude_picks = {p.person: p for p in claude_week.picks} if claude_week and claude_week.aker_on else {}
    rows = []
    for person in PEOPLE:
        claude = claude_picks.get(person)
        jev = jev_week.pick_for(person) if jev_week else None
        claude_team = claude.team if claude else NO_TEAM
        jev_team = _jev_team(jev_week, jev)
        if claude_team == NO_TEAM and jev_team == NO_TEAM:
            continue
        market = claude.market if claude else jev.market
        rows.append(ReviewRow(
            matchday=matchday,
            person=person,
            status=_status(claude_team, jev_team, claude, jev),
            claude_team=claude_team,
            jev_team=jev_team,
            jev_confidence=round(jev.team_confidence, 2) if jev else None,
            jev_alternatives="; ".join(f"{t} {p:.2f}" for t, p in jev.team_alternatives) if jev else "",
            market=market,
            selection_text=claude.selection_text if claude else "",
            evidence=claude.evidence if claude else "",
            placer=claude_week.placer if claude_week else "",
            notes=claude_week.notes if claude_week else "",
            final_team=claude_team if claude_team != NO_TEAM else jev_team,
            final_market=market,
        ))
    return rows


def compare(claude: Mapping[date, Week], jev: Mapping[date, JevWeek]) -> list[ReviewRow]:
    return [
        row
        for matchday in sorted(claude.keys() | jev.keys())
        for row in _rows_for_week(matchday, claude.get(matchday), jev.get(matchday))
    ]


def write_rows(rows: Sequence[ReviewRow], path: Path) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[fl.name for fl in fields(ReviewRow)])
        writer.writeheader()
        writer.writerows(asdict(r) for r in rows)
