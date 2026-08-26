"""Content-hash based freshness check for incremental re-ingest.

sha256 over the raw fetched text lets ingest_documents() distinguish "URL
already seen, content unchanged" (skip, previous behavior) from "URL already
seen, content changed" (re-chunk/re-embed in place) without re-diffing the
old chunk text.
"""

import hashlib


def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
