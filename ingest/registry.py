"""Source-plugin registry — the seam that lets ingestion be data-type-
generic instead of data-type-specific.

Before this, cli.py's cmd_ingest() was an if/elif chain naming every source
type by hand, and adding a new source meant editing that chain. Every
fetcher already lived behind a uniform-enough return shape
({"source","url","title","text","license",...}); what was missing was a
uniform *call* shape. Each plugin below adapts one already-existing fetcher
in ingest/sources.py or ingest/loaders.py to the same signature
(fetch(query, max_results, config, path) -> list[dict], using only the
kwargs it actually needs) so a caller — the CLI, the ingest microservice's
scheduler, or a future consumer — can drive any source through one
interface: REGISTRY[name].fetch(...).

interval_minutes is the plugin's default polling interval for
ingest_service's scheduler (see ingest_service/server.py) — not used by
the CLI at all, which stays purely on-demand.
"""

from dataclasses import dataclass
from typing import Callable

from ingest.loaders import fetch_local_files
from ingest.sources import (
    fetch_arxiv,
    fetch_arxiv_seed,
    fetch_maib,
    fetch_ntm,
    fetch_ntsb,
    fetch_pdf_sources,
    fetch_wikipedia,
)


@dataclass
class SourcePlugin:
    name: str
    fetch: Callable[..., list[dict]]
    description: str
    interval_minutes: int = 1440  # default: once a day
    needs_path: bool = False  # true only for --source file, which has no default to poll


def _fetch_arxiv(*, query: str | None = None, max_results: int = 20, **_) -> list[dict]:
    return fetch_arxiv(query, max_results) if query else fetch_arxiv_seed()


def _fetch_wikipedia(**_) -> list[dict]:
    return fetch_wikipedia()


def _fetch_maib(*, max_results: int = 30, **_) -> list[dict]:
    return fetch_maib(max_results)


def _fetch_ntm(*, max_results: int = 10, **_) -> list[dict]:
    return fetch_ntm(max_results)


def _fetch_ntsb(*, max_results: int = 30, **_) -> list[dict]:
    return fetch_ntsb(max_results)


def _fetch_pdf(*, config: str = "ingest/sources.yaml", **_) -> list[dict]:
    return fetch_pdf_sources(config)


def _fetch_file(*, path: str | None = None, **_) -> list[dict]:
    if not path:
        raise ValueError('--source file requires --path (a glob, e.g. "./docs/**/*.pdf")')
    return fetch_local_files(path)


REGISTRY: dict[str, SourcePlugin] = {
    "arxiv": SourcePlugin("arxiv", _fetch_arxiv, "arXiv papers — seed queries or --query", 1440),
    "wikipedia": SourcePlugin(
        "wikipedia", _fetch_wikipedia, "curated maritime-topic articles", 10080
    ),
    "maib": SourcePlugin("maib", _fetch_maib, "UK MAIB casualty reports (Atom feed)", 1440),
    "ntm": SourcePlugin("ntm", _fetch_ntm, "UKHO weekly Notices to Mariners", 10080),
    "ntsb": SourcePlugin("ntsb", _fetch_ntsb, "US NTSB marine reports (CAROL API)", 1440),
    "pdf": SourcePlugin("pdf", _fetch_pdf, "hand-curated sources.yaml (PDF + type: html)", 1440),
    "file": SourcePlugin(
        "file", _fetch_file, "local files via --path (not schedulable)", 0, needs_path=True
    ),
}


def fetch(source: str, **kwargs) -> list[dict]:
    plugin = REGISTRY.get(source)
    if plugin is None:
        raise ValueError(f"unknown source: {source!r} (known: {sorted(REGISTRY)})")
    return plugin.fetch(**kwargs)
