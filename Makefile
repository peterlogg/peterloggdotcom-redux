# aker pipeline. Make owns file locations and the dependency graph; `aker` commands are pure-ish steps.
#
#   make              parse chat, fetch results, compare extractors (no paid API calls)
#   make extract      run the Claude + Jev extractors on any new matchdays (paid)
#   make referee      careful Claude pass on disputed / non-win weeks (paid)
#   make pull / push  sync private data with the GCS bucket
#   make refresh      re-download the current season's results

-include .env          # ANTHROPIC_API_KEY, TYPESAFE_API_KEY (gitignored)
export

DATA     := data
RAW      := $(DATA)/raw
INTERIM  := $(DATA)/interim
RESULTS  := $(DATA)/results
BUCKET   := gs://peterloggdotcom-redux

CHAT     := $(RAW)/_chat.txt
MESSAGES := $(INTERIM)/messages.csv
CLAUDE   := $(INTERIM)/picks_claude.jsonl
JEV      := $(INTERIM)/picks_jev.jsonl
REFEREED := $(INTERIM)/picks_refereed.jsonl
RESULTS_CSV := $(DATA)/results.csv
REVIEW   := $(DATA)/picks_review.csv

AKER     := uv run --project pipeline aker

SEASONS  := 1617 1718 1819 1920 2021 2122 2223 2324 2425 2526 2627
CURRENT  := 2627
LEAGUES  := E0 E1 E2 E3 EC SC0 SC1 SC2 SC3
SEASON_FILES := $(foreach s,$(SEASONS),$(foreach l,$(LEAGUES),$(RESULTS)/$(s)_$(l).csv))

.PHONY: all extract referee review push pull refresh
.DELETE_ON_ERROR:

all: review

$(INTERIM) $(RESULTS):
	mkdir -p $@

$(MESSAGES): $(CHAT) | $(INTERIM)
	$(AKER) parse $< --out $@

# One file per season × league. An empty file means football-data hasn't published it.
$(RESULTS)/%.csv: | $(RESULTS)
	curl -fsSL -A aker-stats "https://www.football-data.co.uk/mmz4281/$(word 1,$(subst _, ,$*))/$(word 2,$(subst _, ,$*)).csv" -o $@ \
		|| : > $@

$(RESULTS_CSV): $(SEASON_FILES)
	$(AKER) results $^ --out $@

refresh:
	rm -f $(RESULTS)/$(CURRENT)_*.csv
	$(MAKE) $(RESULTS_CSV)

# Extractors append to their output and skip matchdays already done, so these re-run cheaply.
extract: $(MESSAGES) $(RESULTS_CSV)
	$(AKER) extract-claude --messages $(MESSAGES) --results $(RESULTS_CSV) --out $(CLAUDE)
	$(AKER) extract-jev --messages $(MESSAGES) --results $(RESULTS_CSV) --out $(JEV)

referee: $(MESSAGES) $(RESULTS_CSV)
	$(AKER) referee --messages $(MESSAGES) --results $(RESULTS_CSV) --claude $(CLAUDE) --jev $(JEV) --out $(REFEREED)

review: $(REVIEW)
$(REVIEW): $(CLAUDE) $(JEV)
	$(AKER) review --claude $(CLAUDE) --jev $(JEV) --out $@

push:
	gcloud storage rsync --recursive $(RAW) $(BUCKET)/raw
	gcloud storage rsync --recursive $(INTERIM) $(BUCKET)/interim

pull: | $(INTERIM)
	mkdir -p $(RAW)
	gcloud storage rsync --recursive $(BUCKET)/raw $(RAW)
	gcloud storage rsync --recursive $(BUCKET)/interim $(INTERIM)
