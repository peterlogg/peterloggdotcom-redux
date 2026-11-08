# The Aker — peterlogg.com

Ten years of our Saturday accumulator, extracted from the WhatsApp group and settled against real results.

- **Site:** https://peterlogg.com (React + TypeScript + Observable Plot, Firebase Hosting)
- **Admin:** https://peterlogg.com/admin (Google sign-in, admin only) — label missing / doubtful picks
- **Pipeline:** `pipeline/` (Python `aker` package), driven by the `Makefile`

## Routine

```sh
make pull                      # fetch private data (raw chat, media, extractions) from GCS
make labels report queue deploy  # pull /admin labels → rebuild stats → refresh review queue → publish
```

## New WhatsApp export

1. Export the group chat (without media) and save it as `data/raw/_chat.txt`.
2. `make extract referee` — only new matchdays are sent to Claude/Jev (pennies).
3. Optional: drop new bet-slip screenshots in `data/raw/media/`, `make slips-count`, then `make slips`.
4. Label anything new in /admin, then `make labels report queue deploy` and `make push`.

## Setup notes

- `.env` (gitignored): `ANTHROPIC_API_KEY`, `TYPESAFE_API_KEY` — personal keys.
- Firebase project `peterloggdotcom-redux`; private bucket `gs://peterloggdotcom-redux` and the
  `peterlogg.com` Cloud DNS zone live in GCP project `peterlogg-dotcom`.
- gcloud/Firebase commands use the personal account explicitly (this machine's default credentials are a work account).
- Raw chat, media and chat-derived files never go in git, and no chat text goes to Firestore or the site. The only online copy is the private bucket backup; git has picks, labels and the public report.
