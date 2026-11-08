"""Parse the WhatsApp export and group it into one window per Saturday.

Handles iOS ("[08/11/2026, 09:15:32] Name: text") and Android
("08/11/2026, 09:15 - Name: text") formats, plus multi-line messages.
"""
import csv
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import date, datetime, timedelta
from pathlib import Path

from aker.config import FIRST_MATCHDAY, OFF_SEASON_MONTHS, SENDER_ALIASES
from aker.models import ChatWindow, Message

IOS = re.compile(r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2})(?::\d{2})?\]\s*([^:]+?):\s?(.*)$")
ANDROID = re.compile(r"^(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2})\s*-\s*([^:]+?):\s?(.*)$")
INVISIBLE = dict.fromkeys(map(ord, "‎‏‪‬﻿"), None)


def _timestamp(day: str, time: str) -> datetime:
    year_fmt = "%Y" if len(day.rsplit("/", 1)[-1]) == 4 else "%y"
    return datetime.strptime(f"{day} {time}", f"%d/%m/{year_fmt} %H:%M")


def parse_export(path: Path) -> list[Message]:
    """Parse a raw export. Senders are mapped to first names; others (system, Meta AI) are dropped."""
    parsed: list[tuple[datetime, str, list[str]]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.translate(INVISIBLE).replace(" ", " ")
        if m := IOS.match(line) or ANDROID.match(line):
            day, time, sender, text = m.groups()
            parsed.append((_timestamp(day, time), sender, [text]))
        elif parsed:  # continuation of a multi-line message
            parsed[-1][2].append(line)
    return [
        Message(sent_at, SENDER_ALIASES[sender], "\n".join(lines))
        for sent_at, sender, lines in parsed
        if sender in SENDER_ALIASES
    ]


def write_messages(messages: Iterable[Message], path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sent_at", "sender", "text"])
        w.writerows((m.sent_at.isoformat(), m.sender, m.text) for m in messages)


def read_messages(path: Path) -> Iterator[Message]:
    with path.open() as f:
        for row in csv.DictReader(f):
            yield Message(datetime.fromisoformat(row["sent_at"]), row["sender"], row["text"])


def _matchday_for(ts: datetime) -> date | None:
    """The Saturday a message belongs to: Friday from 18:00, or any time on Saturday."""
    if ts.weekday() == 4 and ts.hour >= 18:
        return ts.date() + timedelta(days=1)
    if ts.weekday() == 5:
        return ts.date()
    return None


def matchday_windows(messages: Iterable[Message]) -> list[ChatWindow]:
    first = date.fromisoformat(FIRST_MATCHDAY)
    grouped: dict[date, list[Message]] = defaultdict(list)
    for m in messages:
        day = _matchday_for(m.sent_at)
        if day and day >= first and day.month not in OFF_SEASON_MONTHS:
            grouped[day].append(m)
    return [ChatWindow(day, tuple(msgs)) for day, msgs in sorted(grouped.items())]
