"""Paths and group constants. Paths are relative to the repo root, where the CLI is run from."""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("AKKA_DATA_DIR", "data"))

RAW_CHAT = DATA_DIR / "raw" / "_chat.txt"
INTERIM_DIR = DATA_DIR / "interim"  # gitignored: derived from private messages
MESSAGES_CSV = INTERIM_DIR / "messages.csv"
CLAUDE_PICKS = INTERIM_DIR / "picks_claude.jsonl"
JEV_PICKS = INTERIM_DIR / "picks_jev.jsonl"

RESULTS_DIR = DATA_DIR / "results"
RESULTS_CSV = DATA_DIR / "results.csv"
PICKS_REVIEW_CSV = DATA_DIR / "picks_review.csv"

SENDER_ALIASES = {
    "Pppp🐍🥓💂‍♀️": "Peter",
    "Wotsupmark": "Russell",
    "Wotsupdom": "Dom",
    "Simon Letouze": "Simon",
}
PEOPLE = tuple(sorted(SENDER_ALIASES.values()))

FIRST_SATURDAY = "2016-08-01"  # earliest plausible akka; extractors flag weeks with no bet
OFF_SEASON_MONTHS = frozenset({6, 7})

CLAUDE_MODEL = "claude-opus-5-5"
JEV_MODEL = "jev-latest"
