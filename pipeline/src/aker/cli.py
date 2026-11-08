"""aker CLI. Every command takes explicit input/output paths; the Makefile wires them together."""
import argparse
import logging
from collections import Counter
from pathlib import Path

from aker import chat, extract_claude, extract_jev, picks, referee, report, results, review, settle, slips
from aker.models import ExtractedFile, ImageSlip, JevWeek, RefereedWeek, Week


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


def _missing_matchdays(claude_path: Path, refereed_path: Path, labels_path: Path) -> list:
    claude = ExtractedFile(claude_path, Week).by_matchday()
    refereed = ExtractedFile(refereed_path, RefereedWeek).by_matchday()
    labels = picks.read_labels(labels_path)
    days = picks.aker_matchdays(claude, refereed)
    items = picks.review_items(picks.assemble(claude, refereed, labels), days, labels)
    return sorted({i.matchday for i in items if i.reason == "missing"})


def cmd_slips(a: argparse.Namespace) -> None:
    days = _missing_matchdays(a.claude, a.refereed, a.labels)
    n = slips.read_slips(a.media, days, _clubs(a.results), ExtractedFile(a.out, ImageSlip), a.limit, a.dry_run)
    print(f"read {n} images")


def cmd_queue(a: argparse.Namespace) -> None:
    from aker import admin  # needs gcloud; keep other commands free of it

    claude = ExtractedFile(a.claude, Week).by_matchday()
    refereed = ExtractedFile(a.refereed, RefereedWeek).by_matchday()
    slip_reads = slips.slips_by_matchday(ExtractedFile(a.slips, ImageSlip).read())
    labels = picks.read_labels(a.labels)
    final = picks.assemble(claude, refereed, labels, slip_reads)
    days = picks.aker_matchdays(claude, refereed)
    df = results.load_results(a.results)
    weeks = settle.settle(final, picks.placers(claude, refereed), df)
    no_fixture = [l.pick for w in weeks for l in w.legs if l.fixture is None]
    items = picks.with_no_fixture_flags(picks.review_items(final, days, labels, slip_reads), no_fixture)
    windows = {w.matchday: w for w in _windows(a.messages)}
    pushed, removed = admin.push_queue(items, final, windows, picks.placers(claude, refereed), df)
    print(f"review queue: {pushed} items pushed, {removed} stale removed")


def cmd_labels(a: argparse.Namespace) -> None:
    from aker import admin

    pulled = admin.pull_labels()
    merged = admin.merge_labels(picks.read_labels(a.out), pulled)
    picks.write_labels(merged, a.out)
    print(f"{len(pulled)} labels pulled, {len(merged)} in {a.out}")


def cmd_report(a: argparse.Namespace) -> None:
    claude = ExtractedFile(a.claude, Week).by_matchday()
    refereed = ExtractedFile(a.refereed, RefereedWeek).by_matchday()
    slip_reads = slips.slips_by_matchday(ExtractedFile(a.slips, ImageSlip).read())
    final = picks.assemble(claude, refereed, picks.read_labels(a.labels), slip_reads)
    weeks = settle.settle(final, picks.placers(claude, refereed), results.load_results(a.results))
    built = report.build(weeks)
    report.write(built, a.out)
    s = built.summary
    print(f"{s.weeks} weeks ({s.weeks_won} won), staked £{s.staked:,.0f}, returned £{s.returned:,.2f}, profit £{s.profit:,.2f}")
    print(built.scottish.verdict)


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

    p = sub.add_parser("slips", help="read bet-slip images on matchdays with missing picks")
    for arg in ("--media", "--claude", "--refereed", "--labels", "--results", "--out"):
        p.add_argument(arg, type=Path, required=True)
    p.add_argument("--limit", type=int)
    p.add_argument("--dry-run", action="store_true", help="only count candidate images")
    p.set_defaults(func=cmd_slips)

    p = sub.add_parser("queue", help="push the review queue to Firestore for /admin")
    for arg in ("--messages", "--claude", "--refereed", "--slips", "--labels", "--results"):
        p.add_argument(arg, type=Path, required=True)
    p.set_defaults(func=cmd_queue)

    p = sub.add_parser("labels", help="pull /admin labels from Firestore into the labels CSV")
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=cmd_labels)

    p = sub.add_parser("report", help="final picks → settle → public report JSON")
    for arg in ("--claude", "--refereed", "--slips", "--labels", "--results", "--out"):
        p.add_argument(arg, type=Path, required=True)
    p.set_defaults(func=cmd_report)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.func(args)
