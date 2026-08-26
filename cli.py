import argparse
from datetime import date

import ops_cli
from db.init_db import main as init_db
from ingest.ingest import ingest_documents
from ingest.loaders import fetch_local_files
from ingest.sources import fetch_arxiv, fetch_arxiv_seed, fetch_maib, fetch_ntm, fetch_pdf_sources, fetch_wikipedia
from rag.pipeline import ask
from eval.evaluate import main as run_eval


def cmd_init_db(_args) -> None:
    init_db()


def cmd_ingest(args) -> None:
    if args.source == "arxiv":
        docs = fetch_arxiv(args.query, args.max_results) if args.query else fetch_arxiv_seed()
    elif args.source == "wikipedia":
        docs = fetch_wikipedia()
    elif args.source == "pdf":
        docs = fetch_pdf_sources(args.config)
    elif args.source == "maib":
        docs = fetch_maib(args.max_results)
    elif args.source == "ntm":
        docs = fetch_ntm(args.max_results)
    elif args.source == "file":
        if not args.path:
            raise SystemExit("--source file requires --path (a glob, e.g. \"./docs/**/*.pdf\")")
        docs = fetch_local_files(args.path)
    else:
        raise SystemExit(f"unknown source: {args.source}")

    count = ingest_documents(docs)
    print(f"ingested {count} new document(s) from {len(docs)} fetched ({args.source})")


def cmd_export_sqlite(args) -> None:
    from config import SQLITE_PATH
    from ingest.export_sqlite import export_sqlite

    output = args.output or SQLITE_PATH
    docs, chunks = export_sqlite(output)
    print(f"exported {docs} documents / {chunks} chunks to {output}")


def cmd_ask(args) -> None:
    since = date.fromisoformat(args.since) if args.since else None
    result = ask(
        args.question,
        top_k=args.top_k,
        generate=not args.no_generate,
        rerank=not args.no_rerank,
        since=since,
        source_filter=args.source_filter,
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

        size = export(result, args.question, args.export, args.format)
        print(f"\nwrote {args.export} ({size:,} bytes) — small enough to attach or paste into an email")


def main() -> None:
    parser = argparse.ArgumentParser(description="ship2shore_rag CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create/update the schema (literature + operations tables)").set_defaults(func=cmd_init_db)

    p_ingest = sub.add_parser("ingest", help="pull literature into the corpus from a source (arXiv, Wikipedia, MAIB, NtM, PDF, or local files)")
    p_ingest.add_argument("--source", required=True, choices=["arxiv", "wikipedia", "pdf", "maib", "ntm", "file"])
    p_ingest.add_argument("--query", default=None, help="arxiv search query (omit to run the built-in seed queries)")
    p_ingest.add_argument("--max-results", type=int, default=20)
    p_ingest.add_argument("--config", default="ingest/sources.yaml")
    p_ingest.add_argument("--path", default=None, help="glob for --source file, e.g. \"./docs/**/*.pdf\"")
    p_ingest.set_defaults(func=cmd_ingest)

    p_ask = sub.add_parser("ask", help="ask a question — hybrid retrieval over the corpus, optionally generated into a cited answer")
    p_ask.add_argument("question")
    p_ask.add_argument("--top-k", type=int, default=5)
    p_ask.add_argument("--no-generate", action="store_true")
    p_ask.add_argument("--no-rerank", action="store_true", help="skip the cross-encoder reranking pass, use RRF fusion order as-is")
    p_ask.add_argument("--since", default=None, metavar="YYYY-MM-DD", help="only consider documents published/reported on or after this date (only arxiv/maib have a real date; others are excluded when this is set)")
    p_ask.add_argument("--source-filter", default=None, choices=["arxiv", "wikipedia", "pdf", "maib", "ntm", "file"], help="only consider documents from this ingestion source")
    p_ask.add_argument("--export", default=None, help="write a compact report to this path (.html, .txt, or .md)")
    p_ask.add_argument("--format", default=None, choices=["html", "txt", "md"], help="defaults to --export's extension")
    p_ask.set_defaults(func=cmd_ask)

    p_export = sub.add_parser("export-sqlite", help="snapshot Postgres corpus to a portable SQLite file for vessel deployment")
    p_export.add_argument("--output", default=None, help="defaults to SQLITE_PATH from config")
    p_export.set_defaults(func=cmd_export_sqlite)

    sub.add_parser("eval", help="run the retrieval eval harness (recall@k / MRR against eval/queries.yaml, rerank on vs off)").set_defaults(func=lambda _args: run_eval())

    ops_cli.register(sub)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
