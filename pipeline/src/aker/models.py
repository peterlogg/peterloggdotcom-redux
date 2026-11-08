"""Domain records (dataclasses) and the schema Claude fills in (pydantic, required by LangChain)."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

NO_TEAM = "no_team"
Person = Literal["Dom", "Peter", "Russell", "Simon"]


class Market(StrEnum):
    WIN = "win"
    OVER_GOALS = "over_goals"
    BTTS = "btts"
    DRAW_OR_DOUBLE_CHANCE = "draw_or_double_chance"
    OTHER = "other"


MARKET_DESCRIPTIONS = {
    Market.WIN: "Backing the team to win (the default when they just name a team)",
    Market.OVER_GOALS: "Over N goals in the match (e.g. over 2.5)",
    Market.BTTS: "Both teams to score",
    Market.DRAW_OR_DOUBLE_CHANCE: "A draw, or the team to win or draw",
    Market.OTHER: "Any other market",
}


# --- Chat ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Message:
    sent_at: datetime
    sender: str
    text: str


@dataclass(frozen=True)
class ChatWindow:
    """Friday 18:00 → Saturday 23:59 of chat around one aker Saturday."""

    matchday: date
    messages: tuple[Message, ...]

    @property
    def transcript(self) -> str:
        return "\n".join(f"{m.sent_at:%a %H:%M} {m.sender}: {m.text}" for m in self.messages)


@dataclass(frozen=True)
class Club:
    name: str  # football-data.co.uk name, e.g. "Man United", "Hibernian"
    country: Literal["English", "Scottish"]
    leagues: tuple[str, ...]

    @property
    def description(self) -> str:
        return f"{self.country} club ({', '.join(self.leagues)})"


# --- Claude extraction schema (pydantic: LangChain structured output needs it) -----------------


class Pick(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person: Person
    team: str = Field(description="Canonical club name from the provided list, or no_team")
    market: Market
    selection_text: str = Field(description="The pick as written in chat, e.g. 'Hibs' or 'Rangers and over 2.5'")
    evidence: str = Field(description="Timestamp + message where the final pick was stated")
    confident: bool


class Week(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aker_on: bool = Field(description="True if the group accumulator was organised with picks this Saturday")
    placer: Person | Literal["unknown"]
    picks: list[Pick] = Field(description="One entry per person who made a pick; empty if no aker")
    notes: str = Field(description="Anything odd: picks changed, someone picked for another, bet void, etc.")


# --- Refereed selections: every pick as a list of conditions that must all come true ---------


class ConditionType(StrEnum):
    WIN = "win"  # the named team wins
    DRAW = "draw"  # the match is drawn
    DOUBLE_CHANCE = "double_chance"  # the named team wins or draws
    OVER_GOALS = "over_goals"  # total match goals > line
    UNDER_GOALS = "under_goals"  # total match goals < line
    BTTS = "btts"  # both teams score
    BTTS_NO = "btts_no"  # at least one team fails to score
    TEAM_OVER_GOALS = "team_over_goals"  # the named team's goals > line
    OTHER = "other"  # anything we can't settle from the final score


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ConditionType
    line: float | None = Field(description="Goal line for over/under types, e.g. 2.5; null otherwise")


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person: Person
    team: str = Field(
        description="Canonical club name. For team bets, the team backed; for whole-match bets "
        "(overs, btts, draw), either club in that match, preferring the first one mentioned."
    )
    conditions: list[Condition] = Field(description="All must come true, e.g. 'Rangers and over 2.5' → [win, over_goals 2.5]")
    selection_text: str = Field(description="The pick as written in chat")
    evidence: str = Field(description="Timestamp + message where the final pick was stated")
    confident: bool


class RefereedWeek(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aker_on: bool
    placer: Person | Literal["unknown"]
    selections: list[Selection] = Field(description="One per person who made a pick; empty if no aker")
    notes: str = Field(description="How disputes were resolved, and anything odd")


# --- Jev extraction --------------------------------------------------------------------------


@dataclass(frozen=True)
class JevPick:
    person: str
    picked: float  # P(person named a selection)
    team: str
    team_confidence: float
    team_alternatives: tuple[tuple[str, float], ...]  # top 3 (club, probability)
    market: Market
    market_confidence: float


@dataclass(frozen=True)
class JevWeek:
    aker_on: float  # P(aker organised this week)
    placer: str
    placer_confidence: float
    picks: tuple[JevPick, ...]
    input_tokens: int

    def pick_for(self, person: str) -> JevPick:
        return next(p for p in self.picks if p.person == person)


# --- Storage -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Extracted[W]:
    """One extractor's answer (a Week, JevWeek or RefereedWeek) for one Saturday."""

    matchday: date
    week: W


class ExtractedFile[W]:
    """Append-only JSON-lines file of Extracted[W]; extractors append per week, so runs resume."""

    def __init__(self, path: Path, week_type: type[W]) -> None:
        self.path = path
        self._adapter = TypeAdapter(Extracted[week_type])

    def read(self) -> list[Extracted[W]]:
        if not self.path.exists():
            return []
        return [self._adapter.validate_json(line) for line in self.path.read_text().splitlines()]

    def by_matchday(self) -> dict[date, W]:
        return {e.matchday: e.week for e in self.read()}

    def append(self, records: Iterable[Extracted[W]]) -> int:
        written = 0
        with self.path.open("a") as f:
            for record in records:
                f.write(self._adapter.dump_json(record).decode() + "\n")
                f.flush()
                written += 1
        return written


# --- Review ----------------------------------------------------------------------------------


class ReviewStatus(StrEnum):
    AGREE = "agree"
    LOW_CONFIDENCE = "low_conf"
    DISAGREE = "disagree"


@dataclass(frozen=True)
class ReviewRow:
    matchday: date
    person: str
    status: ReviewStatus
    claude_team: str
    jev_team: str
    jev_confidence: float | None
    jev_alternatives: str
    market: Market
    selection_text: str
    evidence: str
    placer: str
    notes: str
    final_team: str
    final_market: Market
    exclude: bool = field(default=False)
