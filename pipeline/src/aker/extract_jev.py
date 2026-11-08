"""Classify each Saturday's chat window with Jev (TypeSafe System One): typed choices + calibrated confidence.

Only windows not already in picks_jev.jsonl are sent.
"""
import asyncio
import logging
from collections.abc import Sequence

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, SystemOneResponse

from aker.config import JEV_MODEL, JEV_PICKS, PEOPLE
from aker.models import MARKET_DESCRIPTIONS, NO_TEAM, ChatWindow, JevPick, JevWeek, Market
from aker.prompts import AKER_CONTEXT
from aker.results import clubs

log = logging.getLogger(__name__)
CONCURRENCY = 8


def _questions() -> dict[str, Choice | Noul]:
    team_options = {NO_TEAM: "This person did not name a team for the group acca"} | {
        c.name: c.description for c in clubs()
    }
    questions: dict[str, Choice | Noul] = {
        "aker_on": Noul(instructions="The friends organised their group accumulator bet with team picks on this Saturday."),
        "placer": Choice(
            instructions="Who placed (put on) the group accumulator bet this week",
            criteria={p: None for p in PEOPLE} | {"unknown": "Not clear from the chat"},
        ),
    }
    for p in PEOPLE:
        questions[f"{p}_picked"] = Noul(instructions=f"{p} named a team (or selection) for the group accumulator this week.")
        questions[f"{p}_team"] = Choice(
            instructions=f"Which club is {p}'s final pick for the group accumulator", criteria=team_options
        )
        questions[f"{p}_market"] = Choice(
            instructions=f"What kind of bet is {p}'s accumulator selection",
            criteria={m.value: d for m, d in MARKET_DESCRIPTIONS.items()},
        )
    return questions


def _to_week(window: ChatWindow, response: SystemOneResponse) -> JevWeek:
    a = response.answers

    def pick(person: str) -> JevPick:
        team = a[f"{person}_team"]
        market = a[f"{person}_market"]
        top3 = sorted(team.probabilities.items(), key=lambda kv: -kv[1])[:3]
        return JevPick(
            person=person,
            picked=a[f"{person}_picked"].noul,
            team=team.choice,
            team_confidence=team.confidence,
            team_alternatives=tuple((name, round(prob, 3)) for name, prob in top3),
            market=Market(market.choice),
            market_confidence=market.confidence,
        )

    return JevWeek(
        saturday=window.saturday,
        aker_on=a["aker_on"].noul,
        placer=a["placer"].choice,
        placer_confidence=a["placer"].confidence,
        picks=tuple(pick(p) for p in PEOPLE),
        input_tokens=response.usage.input_tokens,
    )


def load_jev_weeks() -> list[JevWeek]:
    if not JEV_PICKS.exists():
        return []
    return [JevWeek.from_json(line) for line in JEV_PICKS.read_text().splitlines()]


async def _extract(todo: Sequence[ChatWindow]) -> int:
    questions = _questions()
    sem = asyncio.Semaphore(CONCURRENCY)

    async def classify(client: AsyncTypeSafeClient, window: ChatWindow) -> JevWeek:
        state = {"context": AKER_CONTEXT, "saturday": window.saturday.isoformat(), "chat": window.transcript}
        async with sem:
            return _to_week(window, await client.system_one(state=state, questions=questions))

    JEV_PICKS.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    async with AsyncTypeSafeClient(model=JEV_MODEL) as client:  # reads TYPESAFE_API_KEY
        tasks = [asyncio.create_task(classify(client, w)) for w in todo]
        with JEV_PICKS.open("a") as f:
            for task in asyncio.as_completed(tasks):
                f.write((await task).to_json() + "\n")
                f.flush()
                written += 1
                if written % 50 == 0:
                    log.info("Jev: %d/%d", written, len(todo))
    return written


def extract(windows: Sequence[ChatWindow]) -> int:
    done = {w.saturday for w in load_jev_weeks()}
    todo = [w for w in windows if w.saturday not in done]
    log.info("Jev: %d windows to classify (%d already done)", len(todo), len(done))
    return asyncio.run(_extract(todo)) if todo else 0
