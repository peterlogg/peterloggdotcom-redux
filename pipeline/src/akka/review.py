"""Merge Claude + Jev extractions into a review sheet.

One row per (Saturday, person) where either model found a pick:
  agree     same club, both confident → auto-accepted
  low_conf  same club, but Jev's confidence is low or Claude flagged it → quick check
  disagree  different clubs → needs a human
Edit final_team / final_market / exclude in data/picks_review.csv.
"""
import csv
from collections import Counter
from dataclasses import asdict, fields

from akka.config import PEOPLE, PICKS_REVIEW_CSV
from akka.extract_claude import load_claude_weeks
from akka.extract_jev import load_jev_weeks
from akka.models import NO_TEAM, ClaudeWeek, JevPick, JevWeek, Pick, ReviewRow, ReviewStatus

JEV_AKKA_THRESHOLD = 0.5
JEV_PICKED_THRESHOLD = 0.5
JEV_CONFIDENCE_THRESHOLD = 0.6


def _jev_team(week: JevWeek | None, pick: JevPick | None) -> str:
    if week and pick and week.akka_on >= JEV_AKKA_THRESHOLD and pick.picked >= JEV_PICKED_THRESHOLD:
        return pick.team
    return NO_TEAM


def _status(claude_team: str, jev_team: str, claude: Pick | None, jev: JevPick | None) -> ReviewStatus:
    if claude_team != jev_team:
        return ReviewStatus.DISAGREE
    if (jev and jev.team_confidence < JEV_CONFIDENCE_THRESHOLD) or (claude and not claude.confident):
        return ReviewStatus.LOW_CONFIDENCE
    return ReviewStatus.AGREE


def _rows_for_week(claude_week: ClaudeWeek | None, jev_week: JevWeek | None) -> list[ReviewRow]:
    saturday = (claude_week or jev_week).saturday
    claude_picks = {p.person: p for p in claude_week.picks} if claude_week and claude_week.akka_on else {}
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
            saturday=saturday,
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


def build_review() -> Counter[ReviewStatus]:
    claude = {w.saturday: w for w in load_claude_weeks()}
    jev = {w.saturday: w for w in load_jev_weeks()}
    rows = [row for sat in sorted(claude.keys() | jev.keys()) for row in _rows_for_week(claude.get(sat), jev.get(sat))]
    with PICKS_REVIEW_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[fl.name for fl in fields(ReviewRow)])
        writer.writeheader()
        writer.writerows(asdict(r) for r in rows)
    return Counter(r.status for r in rows)
