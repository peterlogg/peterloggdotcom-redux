"""aker CLI. Every command takes explicit input/output paths; the Makefile wires them together."""
import argparse
import logging
from collections import Counter
from pathlib import Path

from aker import chat, extract_claude, extract_jev, referee, results, review
from aker.models import ExtractedFile, JevWeek, RefereedWeek, Week


def _windows(messages: Path) -> list:
    return chat.matchday_windows(chat.read_messages(messages))


def _clubs(results_csv: Path) -> tuple:
    return results.clubs(results.load_results(results_csv))


def cmd_parse(a: argparse.Namespace) -> None:
    messages = chat.parse_export(a.chat)
    chat.write_messages(messages, a.out)
    print(f"{len(messages)} messages, {messages[0].sent_at:%Y-%m-%d} → {messages[-1].sent_at:%Y-%m-%d}")
    for sender, n in Counter(m.sender for m in messages).most_common():
        print(f"  {n:6d}  {sender}")


def cmd_results(a: argparse.Namespace) -> None:
    df = results.combine(a.season_files)
    df.to_csv(a.out, index=False)
    print(f"{len(df)} matches, {len(results.clubs(df))} clubs")


def cmd_extract_claude(a: argparse.Namespace) -> None:
    n = extract_claude.extract(_windows(a.messages), _clubs(a.results), ExtractedFile(a.out, Week))
    print(f"Claude: wrote {n} weeks")


def cmd_extract_jev(a: argparse.Namespace) -> None:
    n = extract_jev.extract(_windows(a.messages), _clubs(a.results), ExtractedFile(a.out, JevWeek))
    print(f"Jev: wrote {n} weeks")


def cmd_review(a: argparse.Namespace) -> None:
    rows = review.compare(ExtractedFile(a.claude, Week).by_matchday(), ExtractedFile(a.jev, JevWeek).by_matchday())
    review.write_rows(rows, a.out)
    counts = Counter(r.status for r in rows)
    print(f"{len(rows)} picks: " + ", ".join(f"{s.value}={n}" for s, n in counts.most_common()))


def cmd_referee(a: argparse.Namespace) -> None:
    claude = ExtractedFile(a.claude, Week).by_matchday()
    jev = ExtractedFile(a.jev, JevWeek).by_matchday()
    needed = referee.weeks_needing_referee(review.compare(claude, jev))
    usage = referee.referee(
        _windows(a.messages), _clubs(a.results), claude, jev, needed, ExtractedFile(a.out, RefereedWeek), a.limit
    )
    print(f"refereed {usage.weeks} weeks: {usage.input_tokens:,} in ({usage.cached_input_tokens:,} cached), "
          f"{usage.output_tokens:,} out ≈ ${usage.cost_usd:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="aker")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("parse", help="WhatsApp export → messages CSV")
    p.add_argument("chat", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=cmd_parse)

    p = sub.add_parser("results", help="combine football-data season files → one results CSV")
    p.add_argument("season_files", type=Path, nargs="+")
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=cmd_results)

    for name, func in [("extract-claude", cmd_extract_claude), ("extract-jev", cmd_extract_jev)]:
        p = sub.add_parser(name, help="extract picks per matchday (appends; skips weeks already done)")
        p.add_argument("--messages", type=Path, required=True)
        p.add_argument("--results", type=Path, required=True)
        p.add_argument("--out", type=Path, required=True)
        p.set_defaults(func=func)

    p = sub.add_parser("review", help="compare Claude vs Jev → review CSV")
    p.add_argument("--claude", type=Path, required=True)
    p.add_argument("--jev", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("referee", help="careful Claude pass on disputed / non-win weeks")
    for arg in ("--messages", "--results", "--claude", "--jev", "--out"):
        p.add_argument(arg, type=Path, required=True)
    p.add_argument("--limit", type=int)
    p.set_defaults(func=cmd_referee)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.func(args)
