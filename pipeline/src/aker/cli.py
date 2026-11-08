"""aker CLI. Run from the repo root:

    uv run --project pipeline aker parse            # data/raw/_chat.txt → data/interim/messages.csv
    uv run --project pipeline aker results          # download results + odds
    uv run --project pipeline aker extract-claude   # needs ANTHROPIC_API_KEY
    uv run --project pipeline aker extract-jev      # needs TYPESAFE_API_KEY
    uv run --project pipeline aker review           # merge → data/picks_review.csv
    uv run --project pipeline aker push | pull      # sync data/raw + data/interim with the GCS bucket
"""
import argparse
import logging
import sys
from collections import Counter

from aker import chat, extract_claude, extract_jev, results, review, storage
from aker.config import DATA_DIR, RAW_CHAT


def _parse() -> None:
    messages = chat.parse_export(RAW_CHAT)
    chat.write_messages(messages)
    by_sender = Counter(m.sender for m in messages)
    print(f"{len(messages)} messages, {messages[0].sent_at:%Y-%m-%d} → {messages[-1].sent_at:%Y-%m-%d}")
    for sender, n in by_sender.most_common():
        print(f"  {n:6d}  {sender}")


def _results() -> None:
    df = results.update_results()
    print(f"{len(df)} matches, {len(results.clubs())} clubs")


def _extract_claude() -> None:
    print(f"wrote {extract_claude.extract(chat.saturday_windows())} weeks")


def _extract_jev() -> None:
    print(f"wrote {extract_jev.extract(chat.saturday_windows())} weeks")


def _review() -> None:
    counts = review.build_review()
    print(f"{counts.total()} picks: " + ", ".join(f"{s.value}={n}" for s, n in counts.most_common()))


COMMANDS = {
    "parse": _parse,
    "results": _results,
    "extract-claude": _extract_claude,
    "extract-jev": _extract_jev,
    "review": _review,
    "push": lambda: storage.sync("push"),
    "pull": lambda: storage.sync("pull"),
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="aker")
    parser.add_argument("command", choices=COMMANDS)
    args = parser.parse_args()
    if not DATA_DIR.is_dir():
        sys.exit(f"No {DATA_DIR}/ here: run from the repo root (or set AKER_DATA_DIR).")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    COMMANDS[args.command]()
