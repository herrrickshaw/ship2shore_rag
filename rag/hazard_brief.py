"""Composes a job-hazard-analysis-style brief from the existing retrieval
pipeline: similar past incidents/guidance plus the regulation references
already extracted (ingest/regulation_refs.py) from the passages that
mention them. Retrieval only -- deliberately not a generative risk score
or an ML hazard-prediction model (the shape of the original "Risk
Assessment Tool" pitch); see README's roadmap note on why that's out of
scope for what this project actually is.
"""

from retrieval.retriever import retrieve


def _dedupe_refs(passages: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    refs = []
    for p in passages:
        for r in p.get("regulation_refs") or []:
            key = (r.get("instrument"), r.get("detail"))
            if key in seen:
                continue
            seen.add(key)
            refs.append(r)
    return refs


def hazard_brief(job_description: str, top_k: int = 5, source_filter: str | None = None) -> dict:
    """Returns {"job_description", "passages", "regulation_refs"} -- passages
    are ranked exactly like ask(), regulation_refs is every distinct
    instrument/detail pair mentioned across them, in passage-rank order."""
    passages = retrieve(
        f"hazards and control measures for: {job_description}",
        top_k=top_k,
        source_filter=source_filter,
    )
    return {
        "job_description": job_description,
        "passages": passages,
        "regulation_refs": _dedupe_refs(passages),
    }
