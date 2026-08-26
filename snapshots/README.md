# Vessel deployment snapshots

Portable, single-file copies of the shore-side Postgres corpus — built by
`cli.py export-sqlite`, meant to be copied aboard a vessel and used with
`STORAGE_BACKEND=sqlite` (no Postgres, no network required). See the main
[README's "Shipboard deployment"](../README.md#shipboard-deployment) section
for the full design rationale.

## Current snapshot

| | |
|---|---|
| File | `ship2shore-2026-08-26.sqlite3` |
| Generated | 2026-08-26 |
| Size | 7,393,280 bytes (7.05 MiB) |
| SHA-256 | `ee33c7e962c7bf79b60b468dc888763715be91017c0df5d53e6dc41a96345bea` |
| Documents | 125 |
| Chunks | 1,571 |

### Corpus composition

| Source | Documents | What |
|---|---|---|
| `arxiv` | 97 | Seed queries — general shipping/logistics literature + casualty/accident-analysis research |
| `wikipedia` | 14 | Curated maritime-topic articles |
| `maib` | 7 | UK Marine Accident Investigation Branch reports |
| `pdf` | 3 | Curated NTSB marine accident reports |
| `ntm` | 1 | UKHO ADMIRALTY weekly Notices to Mariners bulletin (current week at generation time) |
| `file` | 3 | Local-file ingestion demo fixtures |

## Verifying the file after transfer

Checksums matter here for the same reason they matter for chart corrections —
a silently truncated or corrupted copy is worse than an obviously missing one.
After copying the file aboard (USB, or over a satellite sync), verify it
before pointing `SQLITE_PATH` at it:

```bash
shasum -a 256 ship2shore-2026-08-26.sqlite3
# should print: ee33c7e962c7bf79b60b468dc888763715be91017c0df5d53e6dc41a96345bea
```

## Using it

```bash
cp snapshots/ship2shore-2026-08-26.sqlite3 /path/on/vessel/ship2shore.sqlite3
```

In the vessel's `.env`:

```
STORAGE_BACKEND=sqlite
SQLITE_PATH=/path/on/vessel/ship2shore.sqlite3
```

`cli.py ask "..."` then needs nothing else — verified working with Postgres
stopped entirely and with the file copied to an arbitrary path, confirming
it's a genuinely self-contained snapshot with no hidden dependency on where
or how it was generated.

## Regenerating

```bash
python3 cli.py export-sqlite --output snapshots/ship2shore-$(date +%Y-%m-%d).sqlite3
```

Each regeneration is a fresh, complete copy of the corpus at that point in
time — not a diff against the previous snapshot. Because SQLite files don't
compress well as git deltas, this directory will grow by roughly one full
snapshot's size (currently ~7MB) each time it's updated; that's an accepted
tradeoff for a small, personal-scale corpus like this one, worth revisiting
(e.g. only keeping the latest snapshot, or moving to Git LFS) if the corpus
grows substantially larger.
