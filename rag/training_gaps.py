"""Cross-references crew whose STCW certificate is expiring soon
(ops/store.py's list_expiring_certs, which already exists) against the
STCW convention text already ingested and cited via
ingest/regulation_refs.py -- so a training gap doesn't just say "cert
expires in 12 days," it cites the actual convention language that makes
it a requirement. A join across the ops and literature corpora done in
Python, not a new ops table or a new ingestion source.
"""

from ops.store import list_expiring_certs
from retrieval.retriever import retrieve

STCW_QUERY = "STCW certificate renewal and revalidation requirements"


def _stcw_citations(top_k: int) -> list[dict]:
    passages = retrieve(STCW_QUERY, top_k=top_k)
    stcw_only = [
        p
        for p in passages
        if any(r.get("instrument") == "STCW" for r in p.get("regulation_refs") or [])
    ]
    return stcw_only or passages


def training_gaps(days_ahead: int = 30, top_k: int = 2) -> list[dict]:
    """Every currently-aboard crew member with an STCW cert expiring within
    days_ahead, each annotated with the same small set of STCW-citing
    passages (one retrieval call for the batch, not one per crew member --
    the query is the same regardless of whose cert is expiring)."""
    certs = list_expiring_certs(days_ahead=days_ahead)
    if not certs:
        return []
    citations = _stcw_citations(top_k)
    return [{**c, "stcw_citations": citations} for c in certs]
