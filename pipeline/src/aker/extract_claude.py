"""Extract each Saturday's aker picks with Claude, via LangChain structured output.

Only windows not already in picks_claude.jsonl are sent, so re-running picks up new weeks.
"""
import logging
from collections.abc import Sequence

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from aker.config import CLAUDE_MODEL, CLAUDE_PICKS
from aker.models import NO_TEAM, ChatWindow, ClaudeWeek, Week
from aker.prompts import AKER_CONTEXT
from aker.results import clubs

log = logging.getLogger(__name__)
CONCURRENCY = 8


def _system_prompt() -> str:
    club_list = "\n".join(f"- {c.name}: {c.description}" for c in clubs())
    return (
        f"{AKER_CONTEXT}\n\n"
        "Extract that Saturday's accumulator from the chat. "
        "If someone picked on someone else's behalf, attribute it to the person whose leg it is. "
        "If there's no aker that week (international break, off-season, nobody picks), set aker_on false and picks empty.\n\n"
        f"Use these canonical club names for `team` (or {NO_TEAM} if the selection isn't one of them):\n{club_list}"
    )


def load_claude_weeks() -> list[ClaudeWeek]:
    if not CLAUDE_PICKS.exists():
        return []
    return [ClaudeWeek.model_validate_json(line) for line in CLAUDE_PICKS.read_text().splitlines()]


def _check_teams(week: ClaudeWeek, known: frozenset[str]) -> ClaudeWeek:
    for pick in week.picks:
        if pick.team not in known:
            log.warning("%s %s: unknown club %r → %s", week.saturday, pick.person, pick.team, NO_TEAM)
            pick.team = NO_TEAM
    return week


def extract(windows: Sequence[ChatWindow]) -> int:
    done = {w.saturday for w in load_claude_weeks()}
    todo = [w for w in windows if w.saturday not in done]
    log.info("Claude: %d windows to extract (%d already done)", len(todo), len(done))
    if not todo:
        return 0

    llm = ChatAnthropic(model=CLAUDE_MODEL, max_tokens=16000, output_config={"effort": "medium"})
    chain = llm.with_structured_output(Week, method="json_schema")
    system = SystemMessage(_system_prompt())
    inputs = [[system, HumanMessage(f"Saturday {w.saturday}\n\n{w.transcript}")] for w in todo]
    results = chain.batch(inputs, config={"max_concurrency": CONCURRENCY}, return_exceptions=True)

    known = frozenset(c.name for c in clubs()) | {NO_TEAM}
    written = 0
    CLAUDE_PICKS.parent.mkdir(parents=True, exist_ok=True)
    with CLAUDE_PICKS.open("a") as f:
        for window, result in zip(todo, results, strict=True):
            if isinstance(result, Exception):
                log.error("%s: %s", window.saturday, result)
                continue
            week = _check_teams(ClaudeWeek(saturday=window.saturday, **result.model_dump()), known)
            f.write(week.model_dump_json() + "\n")
            written += 1
    return written
