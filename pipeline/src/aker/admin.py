"""Sync with the /admin page: push the review queue to Firestore, pull human labels back."""
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from datetime import date

import pandas as pd
from google.cloud import firestore
from google.oauth2.credentials import Credentials

from aker.config import FIRESTORE_DATABASE, GCLOUD_ACCOUNT, GCP_PROJECT
from aker.models import Bet, ChatWindow, FinalPick, Label, ReviewItem
from aker.results import LEAGUES

QUEUE = "review_queue"
LABELS = "labels"
MAX_CHAT_CHARS = 20_000


def client() -> firestore.Client:
    token = subprocess.run(
        ["gcloud", "auth", "print-access-token", "--account", GCLOUD_ACCOUNT],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return firestore.Client(project=GCP_PROJECT, database=FIRESTORE_DATABASE, credentials=Credentials(token))


def _doc_id(matchday: date, person: str) -> str:
    return f"{matchday.isoformat()}_{person}"


def _pick(p: FinalPick | None) -> dict | None:
    if p is None:
        return None
    return {"team": p.team, "bets": [str(b) for b in p.bets], "selection_text": p.selection_text, "source": p.source.value}


def _fixtures(results: pd.DataFrame, day: date) -> list[dict]:
    games = results[results["Date"].dt.date == day]
    return [
        {"home": r.HomeTeam, "away": r.AwayTeam, "league": LEAGUES.get(r.League, r.League),
         "score": f"{int(r.FTHG)}-{int(r.FTAG)}" if pd.notna(r.FTHG) else None}
        for r in games.itertuples()
    ]


def push_queue(
    items: Sequence[ReviewItem],
    picks: Sequence[FinalPick],
    windows: Mapping[date, ChatWindow],
    placers: Mapping[date, str],
    results: pd.DataFrame,
) -> tuple[int, int]:
    db = client()
    wanted = {_doc_id(i.matchday, i.person): i for i in items}
    by_day: dict[date, list[FinalPick]] = {}
    for p in picks:
        by_day.setdefault(p.matchday, []).append(p)

    batch, n = db.batch(), 0
    for doc_id, item in wanted.items():
        window = windows.get(item.matchday)
        batch.set(db.collection(QUEUE).document(doc_id), {
            "matchday": item.matchday.isoformat(),
            "person": item.person,
            "reason": item.reason,
            "current": _pick(item.current),
            "slip_teams": list(item.slip_teams),
            "placer": placers.get(item.matchday, "unknown"),
            "week_picks": {p.person: _pick(p) for p in by_day.get(item.matchday, [])},
            "fixtures": _fixtures(results, item.matchday),
            "chat": window.transcript[-MAX_CHAT_CHARS:] if window else "",
        })
        n += 1
        if n % 400 == 0:  # Firestore batches cap at 500 writes
            batch.commit()
            batch = db.batch()
    stale = [d.reference for d in db.collection(QUEUE).stream() if d.id not in wanted]
    for ref in stale:
        batch.delete(ref)
    batch.commit()
    return len(wanted), len(stale)


def pull_labels() -> list[Label]:
    labels = []
    for doc in client().collection(LABELS).stream():
        d = doc.to_dict()
        labels.append(Label(
            matchday=date.fromisoformat(d["matchday"]),
            person=d["person"],
            team=d.get("team") or None,
            bets=tuple(Bet.parse(b) for b in d.get("bets", [])),
        ))
    return labels


def merge_labels(existing: Iterable[Label], pulled: Iterable[Label]) -> list[Label]:
    """Firestore wins over the local file for the same (matchday, person)."""
    merged = {(l.matchday, l.person): l for l in existing}
    merged |= {(l.matchday, l.person): l for l in pulled}
    return list(merged.values())
