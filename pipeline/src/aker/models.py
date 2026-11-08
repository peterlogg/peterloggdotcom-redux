"""Domain records (dataclasses) and the schema Claude fills in (pydantic, required by LangChain)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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

    saturday: date
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


class ClaudeWeek(Week):
    """A Week as stored on disk, keyed by its Saturday."""

    saturday: date


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
    saturday: date
    aker_on: float  # P(aker organised this week)
    placer: str
    placer_confidence: float
    picks: tuple[JevPick, ...]
    input_tokens: int

    def pick_for(self, person: str) -> JevPick:
        return next(p for p in self.picks if p.person == person)

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)

    @classmethod
    def from_json(cls, line: str) -> JevWeek:
        d = json.loads(line)
        picks = tuple(
            JevPick(**{**p, "market": Market(p["market"]), "team_alternatives": tuple(map(tuple, p["team_alternatives"]))})
            for p in d.pop("picks")
        )
        return cls(**{**d, "saturday": date.fromisoformat(d["saturday"]), "picks": picks})


# --- Review ----------------------------------------------------------------------------------


class ReviewStatus(StrEnum):
    AGREE = "agree"
    LOW_CONFIDENCE = "low_conf"
    DISAGREE = "disagree"


@dataclass(frozen=True)
class ReviewRow:
    saturday: date
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
