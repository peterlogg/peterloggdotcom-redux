"""Sync private data folders with the GCS bucket (via the gcloud CLI)."""
import subprocess
from typing import Literal

from aker.config import BUCKET, DATA_DIR, SYNCED_DIRS


def sync(direction: Literal["push", "pull"]) -> None:
    for name in SYNCED_DIRS:
        local, remote = DATA_DIR / name, f"{BUCKET}/{name}"
        src, dst = (str(local), remote) if direction == "push" else (remote, str(local))
        local.mkdir(parents=True, exist_ok=True)
        subprocess.run(["gcloud", "storage", "rsync", "--recursive", src, dst], check=True)
