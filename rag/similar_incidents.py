"""Given an incident/near-miss description, retrieves similar past reports
from the ingested corpus (MAIB/NTSB casualty reports score highest for
this kind of query by content alone, so no source_filter is forced) --
pattern recall at the moment a report is filed, not the predictive ML
model originally scoped. Deliberately a standalone module, not wired into
ops/store.py's write path: ops (CRUD, dependency-light) and rag
(retrieval, embeddings) stay separate concerns here, same split README
draws for the rest of the project -- callers (ops_cli.py, api.py) opt in
explicitly instead of every safety report paying retrieval's cost.
"""

from retrieval.retriever import retrieve


def find_similar_incidents(description: str, top_k: int = 3) -> list[dict]:
    return retrieve(description, top_k=top_k)
