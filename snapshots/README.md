# Vessel deployment snapshots

Portable, single-file copies of the shore-side Postgres corpus — built by
`cli.py export-sqlite`, meant to be copied aboard a vessel and used with
`STORAGE_BACKEND=sqlite` (no Postgres, no network required). See the main
[README's "Shipboard deployment"](../README.md#shipboard-deployment) section
for the full design rationale.

## Current snapshot

Only the latest snapshot is kept — `ship2shore.sqlite3` is overwritten on each
regeneration rather than accumulating a dated file per export.

| | |
|---|---|
| File | `ship2shore.sqlite3` |
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
shasum -a 256 ship2shore.sqlite3
# should print: ee33c7e962c7bf79b60b468dc888763715be91017c0df5d53e6dc41a96345bea
```

## Using it

```bash
cp snapshots/ship2shore.sqlite3 /path/on/vessel/ship2shore.sqlite3
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
python3 cli.py export-sqlite --output snapshots/ship2shore.sqlite3
```

This overwrites the committed file in place — each commit replaces the
previous snapshot rather than adding a new one, so this directory stays at
roughly one snapshot's size regardless of how often it's regenerated. Update
the table above (size, checksum, date, corpus composition) to match whenever
you regenerate and commit a new snapshot.

Note: git history still retains the earlier dated snapshot from before this
policy (`ship2shore-2026-08-26.sqlite3`, one commit) — that's normal git
behavior, not a leftover to clean up; it costs nothing going forward since the
working tree now only ever has the one current file.
