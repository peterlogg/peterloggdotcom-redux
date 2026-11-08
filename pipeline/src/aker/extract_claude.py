"""Extract each Saturday's aker picks with Claude, via LangChain structured output.

Weeks already in the store are skipped, so re-running picks up new weeks only.
"""
import logging
from collections.abc import Sequence

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from aker.config import CLAUDE_MODEL
from aker.models import NO_TEAM, ChatWindow, Club, Extracted, ExtractedFile, Week
from aker.prompts import AKER_CONTEXT

log = logging.getLogger(__name__)
CONCURRENCY = 8


def _system_prompt(clubs: Sequence[Club]) -> str:
    club_list = "\n".join(f"- {c.name}: {c.description}" for c in clubs)
    return (
        f"{AKER_CONTEXT}\n\n"
        "Extract that Saturday's accumulator from the chat. "
        "If someone picked on someone else's behalf, attribute it to the person whose leg it is. "
        "If there's no aker that week (international break, off-season, nobody picks), set aker_on false and picks empty.\n\n"
        f"Use these canonical club names for `team` (or {NO_TEAM} if the selection isn't one of them):\n{club_list}"
    )


def _check_teams(week: Week, known: frozenset[str], matchday: object) -> Week:
    for pick in week.picks:
        if pick.team not in known:
            log.warning("%s %s: unknown club %r → %s", matchday, pick.person, pick.team, NO_TEAM)
            pick.team = NO_TEAM
    return week


def extract(windows: Sequence[ChatWindow], clubs: Sequence[Club], store: ExtractedFile[Week]) -> int:
    done = store.by_matchday().keys()
    todo = [w for w in windows if w.matchday not in done]
    log.info("Claude: %d windows to extract (%d already done)", len(todo), len(done))
    if not todo:
        return 0

    llm = ChatAnthropic(model=CLAUDE_MODEL, max_tokens=16000, output_config={"effort": "medium"})
    chain = llm.with_structured_output(Week, method="json_schema")
    system = SystemMessage(_system_prompt(clubs))
    inputs = [[system, HumanMessage(f"Saturday {w.matchday}\n\n{w.transcript}")] for w in todo]
    outputs = chain.batch(inputs, config={"max_concurrency": CONCURRENCY}, return_exceptions=True)

    known = frozenset(c.name for c in clubs) | {NO_TEAM}
    records = []
    for window, week in zip(todo, outputs, strict=True):
        if isinstance(week, Exception):
            log.error("%s: %s", window.matchday, week)
            continue
        records.append(Extracted(window.matchday, _check_teams(week, known, window.matchday)))
    return store.append(records)
