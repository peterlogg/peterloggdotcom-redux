"""Match results + bookies' odds from football-data.co.uk, and the club list derived from them."""
from functools import cache

import pandas as pd
import requests

from akka.config import RESULTS_CSV, RESULTS_DIR
from akka.models import Club

LEAGUES = {
    "E0": "Premier League", "E1": "Championship", "E2": "League One", "E3": "League Two",
    "EC": "National League", "SC0": "Scottish Premiership", "SC1": "Scottish Championship",
    "SC2": "Scottish League One", "SC3": "Scottish League Two",
}
SEASONS = tuple(f"{y % 100:02d}{(y + 1) % 100:02d}" for y in range(2016, 2026 + 1))
CURRENT_SEASON = SEASONS[-1]
COLUMNS = ["Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
           "B365H", "B365D", "B365A", "AvgH", "AvgD", "AvgA", "B365>2.5", "B365<2.5"]
URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"


def _download(season: str, league: str) -> bool:
    path = RESULTS_DIR / f"{season}_{league}.csv"
    if path.exists() and season != CURRENT_SEASON:  # past seasons never change
        return True
    r = requests.get(URL.format(season=season, league=league), timeout=30, headers={"User-Agent": "akka-stats"})
    if r.status_code != 200 or not r.text.strip():
        return False
    path.write_bytes(r.content)
    return True


def _load(season: str, league: str) -> pd.DataFrame:
    df = pd.read_csv(RESULTS_DIR / f"{season}_{league}.csv", encoding="utf-8-sig",
                     encoding_errors="replace", on_bad_lines="skip")
    df = df[[c for c in COLUMNS if c in df.columns]].dropna(subset=["HomeTeam"])
    return df.assign(League=league, Season=season)  # Div header is BOM-mangled in some files


def update_results() -> pd.DataFrame:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    frames = [_load(s, lg) for s in SEASONS for lg in LEAGUES if _download(s, lg)]
    results = pd.concat(frames, ignore_index=True)
    results["Date"] = pd.to_datetime(results["Date"], dayfirst=True, format="mixed").dt.date
    results.to_csv(RESULTS_CSV, index=False)
    return results


def load_results() -> pd.DataFrame:
    return pd.read_csv(RESULTS_CSV, parse_dates=["Date"], low_memory=False)


@cache
def clubs() -> tuple[Club, ...]:
    leagues_by_club = load_results().groupby("HomeTeam")["League"].unique()
    return tuple(
        Club(
            name=name,
            country="Scottish" if codes[0].startswith("SC") else "English",
            leagues=tuple(LEAGUES[c] for c in sorted(codes)),
        )
        for name, codes in leagues_by_club.items()
    )


def club_names() -> frozenset[str]:
    return frozenset(c.name for c in clubs())
