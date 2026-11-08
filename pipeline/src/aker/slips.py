"""Read bet-slip screenshots (from Google Photos / WhatsApp media) to fill picks missing from the chat text.

Only images dated on a matchday with a missing pick (or the Friday before) are sent to Claude.
"""
import base64
import json
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from aker.config import CLAUDE_MODEL
from aker.models import NO_TEAM, Club, Extracted, ExtractedFile, ImageSlip, SlipRead

log = logging.getLogger(__name__)
CONCURRENCY = 6
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
MAX_BYTES = 5_000_000
WHATSAPP_NAME = re.compile(r"(?:^|[-_])(20\d{6})(?=[-_.])")  # IMG-20231104-WA…, Screenshot_20231104-…, PXL_20231104_…


def image_date(path: Path) -> date | None:
    """Date from a WhatsApp-style filename, else from a Google Takeout JSON sidecar."""
    if m := WHATSAPP_NAME.search(path.name):
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    for sidecar in path.parent.glob(f"{path.name}*.json"):
        meta = json.loads(sidecar.read_text())
        if ts := meta.get("photoTakenTime", {}).get("timestamp"):
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
    return None


def candidate_images(media_dir: Path, matchdays: Iterable[date]) -> dict[Path, date]:
    """Images taken on a matchday (or the Friday before), mapped to that matchday."""
    wanted = {d: d for d in matchdays} | {d - timedelta(days=1): d for d in matchdays}
    found = {}
    for path in sorted(media_dir.rglob("*")):
        if path.suffix.lower() in IMAGE_TYPES and path.stat().st_size <= MAX_BYTES:
            if (taken := image_date(path)) and taken in wanted:
                found[path] = wanted[taken]
    return found


def _system_prompt(clubs: Sequence[Club]) -> str:
    club_list = "\n".join(f"- {c.name}" for c in clubs)
    return (
        "You read screenshots shared in a group chat of four friends who place a weekly football accumulator. "
        "Most images are unrelated (memes, photos). If the image is a bookmaker bet slip or bet confirmation, "
        "extract every leg: the club, the bet as conditions (bare team = [win]; 'over 2.5 goals' = [over_goals 2.5]; "
        "'both teams to score' = [btts]; 'double chance' = [double_chance]; 'draw' = [draw]), and decimal odds. "
        f"Use these canonical club names, or {NO_TEAM} if the selection isn't one of them:\n{club_list}"
    )


def _message(path: Path, matchday: date) -> list:
    data = base64.b64encode(path.read_bytes()).decode()
    url = f"data:{IMAGE_TYPES[path.suffix.lower()]};base64,{data}"
    return [
        {"type": "image_url", "image_url": {"url": url}},
        {"type": "text", "text": f"Shared around Saturday {matchday}. Is this a bet slip? If so, extract it."},
    ]


def read_slips(
    media_dir: Path, matchdays: Sequence[date], clubs: Sequence[Club], store: ExtractedFile[ImageSlip],
    limit: int | None = None, dry_run: bool = False,
) -> int:
    done = {e.week.image for e in store.read()}
    candidates = {p: d for p, d in candidate_images(media_dir, matchdays).items() if p.name not in done}
    todo = list(candidates.items())[:limit]
    log.info("Slips: %d candidate images on %d matchdays (%d already read)",
             len(candidates), len(set(candidates.values())), len(done))
    if dry_run or not todo:
        return 0

    llm = ChatAnthropic(model=CLAUDE_MODEL, max_tokens=8000, output_config={"effort": "low"})
    chain = llm.with_structured_output(SlipRead, method="json_schema")
    system = SystemMessage([{"type": "text", "text": _system_prompt(clubs), "cache_control": {"type": "ephemeral"}}])
    inputs = [[system, HumanMessage(_message(path, day))] for path, day in todo]
    first = chain.batch(inputs[:1], return_exceptions=True)
    outputs = first + chain.batch(inputs[1:], config={"max_concurrency": CONCURRENCY}, return_exceptions=True)

    records = []
    for (path, day), slip in zip(todo, outputs, strict=True):
        if isinstance(slip, Exception):
            log.error("%s: %s", path.name, slip)
            continue
        records.append(Extracted(day, ImageSlip(path.name, slip)))
    found = sum(r.week.slip.is_bet_slip for r in records)
    log.info("Slips: %d of %d images were bet slips", found, len(records))
    return store.append(records)


def slips_by_matchday(slips: Iterable[Extracted[ImageSlip]]) -> Mapping[date, list[SlipRead]]:
    out: dict[date, list[SlipRead]] = {}
    for e in slips:
        if e.week.slip.is_bet_slip and e.week.slip.legs:
            out.setdefault(e.matchday, []).append(e.week.slip)
    return out
