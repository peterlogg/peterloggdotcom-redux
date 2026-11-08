"""Group and model constants. File locations live in the Makefile."""

SENDER_ALIASES = {
    "Pppp🐍🥓💂‍♀️": "Peter",
    "Wotsupmark": "Russell",
    "Wotsupdom": "Dom",
    "Simon Letouze": "Simon",
}
PEOPLE = tuple(sorted(SENDER_ALIASES.values()))

FIRST_MATCHDAY = "2016-08-01"  # earliest plausible aker; extractors flag weeks with no bet
OFF_SEASON_MONTHS = frozenset({6, 7})

CLAUDE_MODEL = "claude-opus-5-5"
JEV_MODEL = "jev-latest"

# Admin (Firebase/Firestore) - personal GCP project, accessed with the personal gcloud login explicitly
# (application-default credentials on this machine belong to a work account).
GCP_PROJECT = "peterlogg-dotcom"
FIRESTORE_DATABASE = "aker"
GCLOUD_ACCOUNT = "loggpeter@googlemail.com"
