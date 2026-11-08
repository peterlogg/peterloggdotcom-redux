"""Second, careful Claude pass over weeks where the extractors disagree or a pick isn't a plain win.

Claude sees the chat plus both extractors' answers and returns every pick as structured conditions,
so it can be settled against the final score. Weeks already refereed are skipped.
"""
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from aker.config import CLAUDE_MODEL
from aker.models import (
    NO_TEAM, ChatWindow, Club, Extracted, ExtractedFile, JevWeek, Market, RefereedWeek, ReviewRow, ReviewStatus, Week,
)
from aker.prompts import AKER_CONTEXT

log = logging.getLogger(__name__)
CONCURRENCY = 6


@dataclass(frozen=True)
class Usage:
    weeks: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int

    @property
    def cost_usd(self) -> float:  # Claude Opus 5.5: $4 in, $0.40 cached read, $20 out per MTok
        uncached = self.input_tokens - self.cached_input_tokens
        return (uncached * 4 + self.cached_input_tokens * 0.4 + self.output_tokens * 20) / 1e6


def _system_prompt(clubs: Sequence[Club]) -> str:
    club_list = "\n".join(f"- {c.name}: {c.description}" for c in clubs)
    return (
        f"{AKER_CONTEXT}\n\n"
        "Two automated extractors have already read this chat and you'll see their answers. They may disagree "
        "or be wrong; the chat is the source of truth. Decide each person's final selection for the group accumulator.\n\n"
        "Express each selection as conditions that must all come true for that leg to win:\n"
        "- A bare team name means [win].\n"
        "- 'X or draw' / 'X double chance' → [double_chance]. 'X v Y draw' → [draw].\n"
        "- 'X over 2.5' / 'X Y over 2 goals' → [over_goals 2.5] on that match ('over two goals' means 2.5).\n"
        "- 'X and over 2.5' → [win, over_goals 2.5]. 'BTTS' / 'both to score' → [btts].\n"
        "- Anything you can't express → [other], and explain in notes.\n"
        "If someone picked on another's behalf, attribute it to the person whose leg it is. "
        "Leave a person out if they made no pick (e.g. it was only in an image).\n\n"
        f"Use these canonical club names (or {NO_TEAM}):\n{club_list}"
    )


def _extractor_summary(claude: Week | None, jev: JevWeek | None) -> str:
    lines = ["Extractor A (LLM):"]
    if claude:
        lines += [f"  aker_on={claude.aker_on} placer={claude.placer}"]
        lines += [f"  {p.person}: {p.team} [{p.market}] '{p.selection_text}' ({p.evidence})" for p in claude.picks]
    lines.append("Extractor B (classifier, probabilities):")
    if jev:
        lines.append(f"  P(aker on)={jev.aker_on:.2f} placer={jev.placer}")
        for p in jev.picks:
            alts = ", ".join(f"{t} {x:.2f}" for t, x in p.team_alternatives)
            lines.append(f"  {p.person}: P(picked)={p.picked:.2f}; team: {alts}; market={p.market}")
    return "\n".join(lines)


def weeks_needing_referee(rows: Sequence[ReviewRow]) -> set[date]:
    """Saturdays with any disputed/low-confidence pick, or any pick that isn't a plain win."""
    return {r.matchday for r in rows if r.status != ReviewStatus.AGREE or r.market != Market.WIN}


def referee(
    windows: Sequence[ChatWindow],
    clubs: Sequence[Club],
    claude: Mapping[date, Week],
    jev: Mapping[date, JevWeek],
    needed: set[date],
    store: ExtractedFile[RefereedWeek],
    limit: int | None = None,
) -> Usage:
    done = store.by_matchday().keys()
    todo = [w for w in windows if w.matchday in needed and w.matchday not in done][:limit]
    log.info("Referee: %d weeks to do (%d needed, %d done)", len(todo), len(needed), len(done))
    if not todo:
        return Usage(0, 0, 0, 0)

    # Cache the long system prompt (club list) across requests.
    system = SystemMessage([{"type": "text", "text": _system_prompt(clubs), "cache_control": {"type": "ephemeral"}}])
    llm = ChatAnthropic(model=CLAUDE_MODEL, max_tokens=16000, output_config={"effort": "medium"})
    chain = llm.with_structured_output(RefereedWeek, method="json_schema", include_raw=True)
    inputs = [
        [system, HumanMessage(
            f"Saturday {w.matchday}\n\n{_extractor_summary(claude.get(w.matchday), jev.get(w.matchday))}\n\nChat:\n{w.transcript}"
        )]
        for w in todo
    ]
    # Send one request first so the cached prompt exists before the concurrent rest arrive.
    first = chain.batch(inputs[:1], return_exceptions=True)
    outputs = first + chain.batch(inputs[1:], config={"max_concurrency": CONCURRENCY}, return_exceptions=True)

    known = frozenset(c.name for c in clubs) | {NO_TEAM}
    tokens_in = tokens_cached = tokens_out = 0
    records = []
    for window, out in zip(todo, outputs, strict=True):
        if isinstance(out, Exception) or out["parsing_error"] or out["parsed"] is None:
            log.error("%s: %s", window.matchday, out if isinstance(out, Exception) else out["parsing_error"])
            continue
        usage = out["raw"].usage_metadata
        tokens_in += usage["input_tokens"]
        tokens_cached += usage.get("input_token_details", {}).get("cache_read", 0)
        tokens_out += usage["output_tokens"]
        week: RefereedWeek = out["parsed"]
        for s in week.selections:
            if s.team not in known:
                log.warning("%s %s: unknown club %r", window.matchday, s.person, s.team)
        records.append(Extracted(window.matchday, week))
    return Usage(store.append(records), tokens_in, tokens_cached, tokens_out)
