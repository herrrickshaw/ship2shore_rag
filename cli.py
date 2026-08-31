import argparse
from datetime import date

import ops_cli
from db.init_db import main as init_db
from eval.evaluate import main as run_eval
from ingest.ingest import ingest_documents
from ingest.registry import REGISTRY
from ingest.registry import fetch as fetch_source
from rag.pipeline import ask


def cmd_init_db(_args) -> None:
    init_db()


def cmd_ingest(args) -> None:
    try:
        docs = fetch_source(
            args.source,
            query=args.query,
            max_results=args.max_results,
            config=args.config,
            path=args.path,
        )
    except ValueError as e:
        raise SystemExit(str(e)) from e

    count = ingest_documents(docs)
    print(f"ingested {count} new document(s) from {len(docs)} fetched ({args.source})")


def cmd_serve(_args) -> None:
    import os

    import uvicorn

    from webui.server import app

    host = os.environ.get("WEBUI_HOST", "127.0.0.1")
    port = int(os.environ.get("WEBUI_PORT", "8020"))
    print(f"serving web UI at http://{host}:{port} (set WEBUI_HOST/WEBUI_PORT to change)")
    uvicorn.run(app, host=host, port=port)


def cmd_serve_ingest(_args) -> None:
    import os

    import uvicorn

    from ingest_service.server import app

    host = os.environ.get("INGEST_SERVICE_HOST", "127.0.0.1")
    port = int(os.environ.get("INGEST_SERVICE_PORT", "8030"))
    print(
        f"serving ingestion service at http://{host}:{port} "
        "(set INGEST_SERVICE_HOST/INGEST_SERVICE_PORT to change) — "
        "GET /sources, POST /sources/{name}/ingest, GET /runs"
    )
    uvicorn.run(app, host=host, port=port)


def cmd_export_sqlite(args) -> None:
    from config import SQLITE_PATH
    from ingest.export_sqlite import export_sqlite

    output = args.output or SQLITE_PATH
    docs, chunks = export_sqlite(output)
    print(f"exported {docs} documents / {chunks} chunks to {output}")


def _port_question(port: str) -> str:
    return (
        f"What are the navigational hazards, chokepoint security concerns, and regulatory "
        f"requirements a vessel should be aware of at or near {port}?"
    )


def cmd_ask(args) -> None:
    question = args.question or (_port_question(args.port) if args.port else None)
    if question is None:
        raise SystemExit("cli.py ask: provide a question, or --port <name> to build one")

    since = date.fromisoformat(args.since) if args.since else None
    result = ask(
        question,
        top_k=args.top_k,
        generate=not args.no_generate,
        rerank=not args.no_rerank,
        since=since,
        source_filter=args.source_filter,
        checklist=args.checklist,
    )
    if result["answer"]:
        print(result["answer"])
        print()
    print("Sources:")
    for i, p in enumerate(result["passages"], 1):
        print(f"[{i}] {p['title']} ({p['url']}) — score {p['score']:.4f}")
        if not result["answer"]:
            print(f"    {p['content'][:300]}...")

    if args.export:
        from rag.export import export

        size = export(result, question, args.export, args.format)
        print(
            f"\nwrote {args.export} ({size:,} bytes) — small enough to attach or paste into an email"
        )


def cmd_hazard_brief(args) -> None:
    from rag.hazard_brief import hazard_brief

    brief = hazard_brief(args.job_description, top_k=args.top_k, source_filter=args.source_filter)
    print(f"Hazard brief: {brief['job_description']}\n")

    if brief["regulation_refs"]:
        print("Governing regulations (from retrieved passages):")
        for r in brief["regulation_refs"]:
            detail = f" {r['detail']}" if r.get("detail") else ""
            print(f"  - {r['instrument']}{detail}")
        print()

    print("Similar past incidents / relevant guidance:")
    for i, p in enumerate(brief["passages"], 1):
        print(f"[{i}] {p['title']} ({p['url']}) — score {p['score']:.4f}")

    if args.export:
        from rag.export import export

        result = {"answer": None, "passages": brief["passages"]}
        size = export(result, brief["job_description"], args.export, args.format)
        print(f"\nwrote {args.export} ({size:,} bytes)")


def cmd_training_gaps(args) -> None:
    from rag.training_gaps import training_gaps

    gaps = training_gaps(days_ahead=args.days)
    if not gaps:
        print(f"no STCW certificates expiring within {args.days} days")
        return
    for g in gaps:
        print(
            f"#{g['id']}  {g['name']:<20} {g['rank']:<20} {g['vessel_name']:<20} "
            f"expires {g['stcw_cert_expiry']}"
        )
        for c in g["stcw_citations"]:
            print(f"    cites: {c['title']} ({c['url']})")


def main() -> None:
    parser = argparse.ArgumentParser(description="ship2shore_rag CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "init-db", help="create/update the schema (literature + operations tables)"
    ).set_defaults(func=cmd_init_db)

    p_ingest = sub.add_parser(
        "ingest",
        help="pull literature into the corpus from a source (arXiv, Wikipedia, MAIB, NtM, PDF, or local files)",
    )
    p_ingest.add_argument(
        "--source",
        required=True,
        choices=sorted(REGISTRY),
    )
    p_ingest.add_argument(
        "--query", default=None, help="arxiv search query (omit to run the built-in seed queries)"
    )
    p_ingest.add_argument("--max-results", type=int, default=20)
    p_ingest.add_argument("--config", default="ingest/sources.yaml")
    p_ingest.add_argument(
        "--path", default=None, help='glob for --source file, e.g. "./docs/**/*.pdf"'
    )
    p_ingest.set_defaults(func=cmd_ingest)

    p_ask = sub.add_parser(
        "ask",
        help="ask a question — hybrid retrieval over the corpus, optionally generated into a cited answer",
    )
    p_ask.add_argument("question", nargs="?", default=None, help="omit when using --port")
    p_ask.add_argument(
        "--port",
        default=None,
        help="shortcut: build a navigational/regulatory briefing question for this port or "
        'strait, e.g. "Strait of Hormuz" (composes on top of already-ingested sources — no new '
        "retrieval)",
    )
    p_ask.add_argument(
        "--checklist",
        action="store_true",
        help="structure the generated answer as an ordered, cited checklist instead of prose "
        "(no effect without generation)",
    )
    p_ask.add_argument("--top-k", type=int, default=5)
    p_ask.add_argument("--no-generate", action="store_true")
    p_ask.add_argument(
        "--no-rerank",
        action="store_true",
        help="skip the cross-encoder reranking pass, use RRF fusion order as-is",
    )
    p_ask.add_argument(
        "--since",
        default=None,
        metavar="YYYY-MM-DD",
        help="only consider documents published/reported on or after this date (only arxiv/maib have a real date; others are excluded when this is set)",
    )
    p_ask.add_argument(
        "--source-filter",
        default=None,
        choices=sorted(REGISTRY),
        help="only consider documents from this ingestion source",
    )
    p_ask.add_argument(
        "--export", default=None, help="write a compact report to this path (.html, .txt, or .md)"
    )
    p_ask.add_argument(
        "--format",
        default=None,
        choices=["html", "txt", "md"],
        help="defaults to --export's extension",
    )
    p_ask.set_defaults(func=cmd_ask)

    p_hazard = sub.add_parser(
        "hazard-brief",
        help="retrieve similar past incidents + governing regulations for a job description "
        "(retrieval only, not a predictive risk score)",
    )
    p_hazard.add_argument("job_description")
    p_hazard.add_argument("--top-k", type=int, default=5)
    p_hazard.add_argument(
        "--source-filter", default=None, choices=sorted(REGISTRY), help="restrict to one source"
    )
    p_hazard.add_argument(
        "--export", default=None, help="write a compact report to this path (.html, .txt, or .md)"
    )
    p_hazard.add_argument("--format", default=None, choices=["html", "txt", "md"])
    p_hazard.set_defaults(func=cmd_hazard_brief)

    p_training = sub.add_parser(
        "training-gaps",
        help="crew with an STCW cert expiring soon, cited against the ingested STCW convention text",
    )
    p_training.add_argument(
        "--days", type=int, default=30, help="look-ahead window in days (default: 30)"
    )
    p_training.set_defaults(func=cmd_training_gaps)

    p_export = sub.add_parser(
        "export-sqlite",
        help="snapshot Postgres corpus to a portable SQLite file for vessel deployment",
    )
    p_export.add_argument("--output", default=None, help="defaults to SQLITE_PATH from config")
    p_export.set_defaults(func=cmd_export_sqlite)

    sub.add_parser(
        "eval",
        help="run the retrieval eval harness (recall@k / MRR against eval/queries.yaml, rerank on vs off)",
    ).set_defaults(func=lambda _args: run_eval())

    sub.add_parser(
        "serve",
        help="serve the read-only web UI (localhost only by default — see README 'Web UI')",
    ).set_defaults(func=cmd_serve)

    sub.add_parser(
        "serve-ingest",
        help="serve the ingestion microservice — scheduled + on-demand ingestion over HTTP "
        "(localhost only by default — see README 'Ingestion service')",
    ).set_defaults(func=cmd_serve_ingest)

    ops_cli.register(sub)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
