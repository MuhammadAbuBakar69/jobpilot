"""Command line entry point: ``jobpilot <command>``.

    jobpilot add posting.txt          # ingest one posting from a file
    jobpilot add --stdin < posting.txt
    jobpilot list --status interview
    jobpilot move 3 offer
    jobpilot stats
    jobpilot serve --port 8000        # REST API
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import db
from .extract import parse_heuristic, parse_with_llm


def _read_source(args: argparse.Namespace) -> str:
    if args.text:
        return args.text
    if args.path:
        return Path(args.path).read_text(encoding="utf-8")
    return sys.stdin.read()


def cmd_add(args: argparse.Namespace) -> int:
    text = _read_source(args)
    if not text.strip():
        print("nothing to read (pass a file, --text, or pipe text in)", file=sys.stderr)
        return 2
    posting = parse_with_llm(text) if args.llm else parse_heuristic(text)
    conn = db.connect(args.db)
    new_id = db.add(conn, posting.to_dict())
    if new_id is None:
        print("already tracked (same company, role or url)")
        return 0
    role = posting.role or "unknown role"
    company = posting.company or "unknown company"
    print(f"added #{new_id}: {role} @ {company}")
    if posting.deadline:
        print(f"  deadline: {posting.deadline}")
    if posting.skills:
        print(f"  skills:   {', '.join(posting.skills[:8])}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    rows = db.list_applications(conn, status=args.status, limit=args.limit)
    if not rows:
        print("no applications tracked yet")
        return 0
    width = max(len(r["company"]) for r in rows)
    for row in rows:
        company = row["company"].ljust(width)
        deadline = row["deadline"] or "-"
        print(f"#{row['id']:<3} {company}  {row['role'][:38]:<38} {row['status']:<9} {deadline}")
    return 0


def cmd_move(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    try:
        ok = db.update_status(conn, args.id, args.status)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if ok:
        print(f"#{args.id} -> {args.status}")
    else:
        print(f"no application #{args.id}", file=sys.stderr)
    return 0 if ok else 1


def cmd_stats(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    data = db.summary(conn)
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    print(f"total applications : {data['total']}")
    for status, count in data["by_status"].items():
        print(f"  {status:<9} {count}")
    print(f"response rate      : {data['response_rate']}%")
    if data["top_skills"]:
        print("most requested     : " + ", ".join(f"{s} ({n})" for s, n in data["top_skills"]))
    if data["next_deadline"]:
        soon = data["next_deadline"]
        print(f"next deadline      : {soon['deadline']} - {soon['role']} @ {soon['company']}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn  # noqa: PLC0415

    from .api import create_app  # noqa: PLC0415

    uvicorn.run(create_app(args.db), host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobpilot", description="Track job applications from raw posting text."
    )
    parser.add_argument(
        "--db", default=str(db.DEFAULT_DB), help="sqlite file (default: jobpilot.db)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="ingest a posting")
    add.add_argument("path", nargs="?", help="file containing the posting text")
    add.add_argument("--text", help="posting text inline")
    add.add_argument(
        "--llm", action="store_true",
        help="use the LLM extractor when OPENAI_API_KEY is set",
    )
    add.set_defaults(func=cmd_add)

    listing = sub.add_parser("list", help="list tracked applications")
    listing.add_argument("--status", choices=db.STATUSES)
    listing.add_argument("--limit", type=int, default=50)
    listing.set_defaults(func=cmd_list)

    move = sub.add_parser("move", help="change an application's status")
    move.add_argument("id", type=int)
    move.add_argument("status", choices=db.STATUSES)
    move.set_defaults(func=cmd_move)

    stats = sub.add_parser("stats", help="summary numbers")
    stats.add_argument("--json", action="store_true")
    stats.set_defaults(func=cmd_stats)

    serve = sub.add_parser("serve", help="run the REST API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
