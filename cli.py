import argparse

from db.init_db import main as init_db
from ingest.ingest import ingest_documents
from ingest.sources import fetch_arxiv, fetch_pdf_sources, fetch_wikipedia
from rag.pipeline import ask


def cmd_init_db(_args) -> None:
    init_db()


def cmd_ingest(args) -> None:
    if args.source == "arxiv":
        docs = fetch_arxiv(args.query or "container shipping logistics", args.max_results)
    elif args.source == "wikipedia":
        docs = fetch_wikipedia()
    elif args.source == "pdf":
        docs = fetch_pdf_sources(args.config)
    else:
        raise SystemExit(f"unknown source: {args.source}")

    count = ingest_documents(docs)
    print(f"ingested {count} new document(s) from {len(docs)} fetched ({args.source})")


def cmd_ask(args) -> None:
    result = ask(args.question, top_k=args.top_k, generate=not args.no_generate)
    if result["answer"]:
        print(result["answer"])
        print()
    print("Sources:")
    for i, p in enumerate(result["passages"], 1):
        print(f"[{i}] {p['title']} ({p['url']}) — similarity {p['similarity']:.3f}")
        if not result["answer"]:
            print(f"    {p['content'][:300]}...")


def main() -> None:
    parser = argparse.ArgumentParser(description="ship2shore_rag CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db").set_defaults(func=cmd_init_db)

    p_ingest = sub.add_parser("ingest")
    p_ingest.add_argument("--source", required=True, choices=["arxiv", "wikipedia", "pdf"])
    p_ingest.add_argument("--query", default=None, help="arxiv search query")
    p_ingest.add_argument("--max-results", type=int, default=20)
    p_ingest.add_argument("--config", default="ingest/sources.yaml")
    p_ingest.set_defaults(func=cmd_ingest)

    p_ask = sub.add_parser("ask")
    p_ask.add_argument("question")
    p_ask.add_argument("--top-k", type=int, default=5)
    p_ask.add_argument("--no-generate", action="store_true")
    p_ask.set_defaults(func=cmd_ask)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
