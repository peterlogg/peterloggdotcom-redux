"""Match results + bookies' odds from football-data.co.uk (downloaded by the Makefile), and the club list."""
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from aker.models import Club

LEAGUES = {
    "E0": "Premier League", "E1": "Championship", "E2": "League One", "E3": "League Two",
    "EC": "National League", "SC0": "Scottish Premiership", "SC1": "Scottish Championship",
    "SC2": "Scottish League One", "SC3": "Scottish League Two",
}
COLUMNS = ["Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
           "B365H", "B365D", "B365A", "AvgH", "AvgD", "AvgA", "B365>2.5", "B365<2.5"]


def _read_season_file(path: Path) -> pd.DataFrame:
    """Read one `{season}_{league}.csv`. League comes from the name: the Div header is BOM-mangled in some files."""
    season, league = path.stem.split("_")
    df = pd.read_csv(path, encoding="utf-8-sig", encoding_errors="replace", on_bad_lines="skip")
    df = df[[c for c in COLUMNS if c in df.columns]].dropna(subset=["HomeTeam"])
    return df.assign(League=league, Season=season)


def combine(paths: Iterable[Path]) -> pd.DataFrame:
    frames = [_read_season_file(p) for p in paths if p.stat().st_size > 0]  # empty = not published
    results = pd.concat(frames, ignore_index=True)
    results["Date"] = pd.to_datetime(results["Date"], dayfirst=True, format="mixed").dt.date
    return results


def load_results(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["Date"], low_memory=False)


def clubs(results: pd.DataFrame) -> tuple[Club, ...]:
    leagues_by_club = results.groupby("HomeTeam")["League"].unique()
    return tuple(
        Club(
            name=name,
            country="Scottish" if codes[0].startswith("SC") else "English",
            leagues=tuple(LEAGUES[c] for c in sorted(codes)),
        )
        for name, codes in leagues_by_club.items()
    )
