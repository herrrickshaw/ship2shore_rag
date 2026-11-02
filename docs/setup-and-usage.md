## Setup

```bash
# 1. Postgres + pgvector (macOS/Homebrew)
# pgvector's bottle only ships builds for the latest 1-2 Postgres majors, so if
# you're on an older `postgresql@N` this may not have a build for it — that's
# why this project runs its own isolated instance on port 5433 rather than
# reusing whatever Postgres you already have.
brew install postgresql@17 pgvector
LC_ALL="en_US.UTF-8" /opt/homebrew/opt/postgresql@17/bin/pg_ctl \
  -D /opt/homebrew/var/postgresql@17 -l /opt/homebrew/var/postgresql@17/server.log \
  -o "-p 5433" start
/opt/homebrew/opt/postgresql@17/bin/createdb -p 5433 ship2shore

# 2. Python env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env   # DATABASE_URL already points at localhost:5433/ship2shore

# 4. Create the schema (enables the pgvector extension + tables)
python3 cli.py init-db
```

## Usage

```bash
# Ingest from the built-in free sources
python3 cli.py ingest --source arxiv          # runs the seed queries (below) — omit --query for this
python3 cli.py ingest --source wikipedia
python3 cli.py ingest --source maib --max-results 30       # UK casualty reports, via gov.uk's Atom feed
python3 cli.py ingest --source ntsb --max-results 30        # US marine reports, via CAROL's search API
python3 cli.py ingest --source pdf --config ingest/sources.yaml   # anything you curate by hand

# Ingest your own local files — PDF, TXT, Markdown, HTML, Word, Excel, or PowerPoint
python3 cli.py ingest --source file --path "./docs/**/*"

# Ask a question (hybrid dense+keyword retrieval, then Claude if ANTHROPIC_API_KEY is set)
python3 cli.py ask "What drives container freight rate volatility?"

# Just retrieve passages, no generation
python3 cli.py ask "bill of lading vs sea waybill" --no-generate

# Export the answer as a compact report — small enough to attach to or paste
# straight into an email (no external assets, a few KB)
python3 cli.py ask "what caused the Dali allision?" --export briefing.html
python3 cli.py ask "what caused the Dali allision?" --export briefing.txt   # plain-text body instead

# Structure the generated answer as an ordered, cited checklist instead of prose
python3 cli.py ask "steps for enclosed space entry" --checklist

# Shortcut: build a navigational/chokepoint/regulatory question for a port or strait
python3 cli.py ask --port "Strait of Hormuz" --export briefing.html

# Job-hazard brief — similar past incidents + every regulation instrument
# mentioned across them, deduplicated (retrieval only, not a risk score)
python3 cli.py hazard-brief "enclosed space entry on a chemical tanker"
```
