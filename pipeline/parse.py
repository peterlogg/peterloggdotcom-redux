"""Parse a WhatsApp chat export into data/interim/messages.csv (date, time, sender, text).

Handles iOS ("[08/11/2026, 09:15:32] Name: text") and Android
("08/11/2026, 09:15 - Name: text") formats, plus multi-line messages.
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/raw/_chat.txt"
OUT = ROOT / "data/interim/messages.csv"

IOS = re.compile(r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}(?::\d{2})?)\]\s*([^:]+?):\s?(.*)$")
ANDROID = re.compile(r"^(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2})\s*-\s*([^:]+?):\s?(.*)$")
INVISIBLE = dict.fromkeys(map(ord, "‎‏‪‬﻿"), None)


def main() -> None:
    rows: list[list[str]] = []
    for raw in SRC.read_text(encoding="utf-8").splitlines():
        line = raw.translate(INVISIBLE).replace(" ", " ")
        m = IOS.match(line) or ANDROID.match(line)
        if m:
            rows.append(list(m.groups()))
        elif rows:  # continuation of a multi-line message
            rows[-1][3] += "\n" + line
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "time", "sender", "text"])
        w.writerows(rows)
    senders: dict[str, int] = {}
    for r in rows:
        senders[r[2]] = senders.get(r[2], 0) + 1
    print(f"{len(rows)} messages, {rows[0][0]} → {rows[-1][0]}" if rows else "no messages parsed")
    for s, n in sorted(senders.items(), key=lambda x: -x[1]):
        print(f"  {n:6d}  {s}")


if __name__ == "__main__":
    main()
