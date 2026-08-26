"""Extracts real regulation/instrument references already present in chunk
text -- IMO conventions (with annex/chapter/regulation detail and amendment
years, when stated) and US CFR citations -- into structured per-chunk
metadata.

Scope, deliberately: this is real extraction of references already
verbatim in the text, not a temporal knowledge graph that models which
version of a regulation superseded which (the DNV RuleAgent / Vibylabs
pattern from the market survey -- see README "Not yet done"). That's a
materially larger project (it needs a maintained model of every
instrument's amendment history, not just what one passage happens to say).
This is the honestly-achievable slice: structure what's already there.

Known limitation, checked and currently harmless: short acronyms (MLC,
SAR) match on bare text, so an unrelated proper noun containing one as a
substring (e.g. a hypothetical vessel "MLC Trader") would false-positive.
Checked against every real chunk in this corpus containing a bare "MLC" --
all 4 are genuinely about the Maritime Labour Convention, none are a name
collision. Not engineering NER/disambiguation for a risk that doesn't
currently manifest in real data; worth revisiting if it ever does.
"""

import re

# Matched against real corpus content (IMO convention pages, NTSB/MAIB
# reports) ingested this session -- not a speculative list. Longer/more
# specific names first so e.g. "MARPOL" doesn't shadow "MARPOL Annex VI"
# matching twice.
INSTRUMENTS = [
    "SOLAS",
    "MARPOL",
    "STCW",
    "COLREGS",
    "COLREG",
    "ISM Code",
    "ISPS Code",
    "MLC",
    "BWM Convention",
    "SAR Convention",
    "Load Lines Convention",
]
_INSTRUMENT_RE = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in INSTRUMENTS) + r")\b", re.IGNORECASE
)
_ANNEX_RE = re.compile(r"\bAnnex\s+([IVX]+)\b", re.IGNORECASE)
_CHAPTER_RE = re.compile(r"\bChapter\s+([IVX]+(?:-\d+)?)\b", re.IGNORECASE)
_REGULATION_RE = re.compile(r"\bRegulation\s+([A-Z]?[\d/.-]+)\b")
_YEAR_AMENDMENT_RE = re.compile(r"\b(\d{4})\s+(Protocol|amendments?|revision)\b", re.IGNORECASE)
_CFR_RE = re.compile(r"\b(\d+)\s+CFR\s+([\d.\-]+)\b")

# How far (chars) an Annex/Chapter/Regulation/year detail may sit from the
# instrument name it's describing and still count as "about" that mention --
# same sentence, roughly; too far apart and it's more likely a different
# clause's detail, not this instrument's.
_PROXIMITY_CHARS = 80


def _nearest_detail(pattern: re.Pattern, text: str, pos: int) -> str | None:
    best = None
    best_dist = _PROXIMITY_CHARS + 1
    for m in pattern.finditer(text):
        dist = abs(m.start() - pos)
        if dist < best_dist:
            best_dist = dist
            best = m
    return best.group(0) if best else None


def _nearest_year(text: str, pos: int) -> int | None:
    best = None
    best_dist = _PROXIMITY_CHARS + 1
    for m in _YEAR_AMENDMENT_RE.finditer(text):
        dist = abs(m.start() - pos)
        if dist < best_dist:
            best_dist = dist
            best = m
    return int(best.group(1)) if best else None


def extract_refs(text: str) -> list[dict]:
    """Returns [{"instrument", "detail", "year", "raw"}, ...] for every
    distinct regulation reference found. "detail" is an Annex/Chapter/
    Regulation qualifier near the instrument mention, or None. "year" is a
    nearby amendment/protocol year, or None. CFR citations are returned
    with instrument="CFR", detail=the section number, year=None."""
    refs: list[dict] = []
    seen: set[tuple] = set()

    for m in _INSTRUMENT_RE.finditer(text):
        instrument = m.group(1).upper() if len(m.group(1)) <= 6 else m.group(1)
        detail = (
            _nearest_detail(_ANNEX_RE, text, m.start())
            or _nearest_detail(_CHAPTER_RE, text, m.start())
            or _nearest_detail(_REGULATION_RE, text, m.start())
        )
        year = _nearest_year(text, m.start())
        key = (instrument, detail, year)
        if key in seen:
            continue
        seen.add(key)
        refs.append({"instrument": instrument, "detail": detail, "year": year, "raw": m.group(0)})

    for m in _CFR_RE.finditer(text):
        key = ("CFR", m.group(0), None)
        if key in seen:
            continue
        seen.add(key)
        refs.append({"instrument": "CFR", "detail": m.group(0), "year": None, "raw": m.group(0)})

    return refs
