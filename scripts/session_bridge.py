#!/usr/bin/env python3
"""session-bridge — search, import, and resume coding-agent sessions across agents.

Read-only over every agent's own session store; the only thing it writes is its
own index (~/.session-bridge/) and the Markdown files you explicitly import.

Usage:
    python session_bridge.py index   [--agents claude,codex] [--force]
    python session_bridge.py search  "<query>" [--agent A] [--project P] [--limit N]
    python session_bridge.py show    <session-id>
    python session_bridge.py import  <session-id> [--to DIR] [--dry-run]
    python session_bridge.py resume  <session-id> [--max-tokens N]
    python session_bridge.py agents
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Make output UTF-8 safe even on Windows consoles defaulting to cp949/cp1252,
# so Markdown, emoji role labels and CJK text never crash the tool.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from adapters import get_adapters, adapter_for          # noqa: E402
from store import Store                                 # noqa: E402
import render                                           # noqa: E402


def _load_full_session(store: Store, session_id: str):
    """Resolve an id to a fully-parsed Session (re-read from its source file)."""
    meta = store.get(session_id)
    if meta is None:
        matches = store.find_by_suffix(session_id)
        if len(matches) == 1:
            meta = matches[0]
        elif len(matches) > 1:
            print("Ambiguous id. Candidates:", file=sys.stderr)
            for m in matches:
                print("  %s  (%s)" % (m["id"], m["title"]), file=sys.stderr)
            return None
        else:
            print("No session with id '%s'. Run `index` first?" % session_id,
                  file=sys.stderr)
            return None
    adapter = adapter_for(meta["agent"])
    if adapter is None:
        print("No adapter for agent '%s'." % meta["agent"], file=sys.stderr)
        return None
    src = Path(meta["source_path"])
    if not src.exists():
        print("Source file is gone: %s" % src, file=sys.stderr)
        return None
    return adapter.parse(src)


def _ensure_indexed(store: Store):
    if store.count() == 0:
        print("Index empty — building it once...", file=sys.stderr)
        store.index()


# --- commands ---------------------------------------------------------------

def cmd_agents(args):
    print("Detected agents on this machine:")
    for adapter in get_adapters():
        mark = "available" if adapter.is_available() else "not found"
        print("  %-8s %-10s %s" % (adapter.name, mark, adapter.root()))
    return 0


def cmd_index(args):
    agents = args.agents.split(",") if args.agents else None
    store = Store()
    stats = store.index(agents=agents, force=args.force)
    store.close()
    print("Indexed %(indexed)d, skipped %(skipped)d, removed %(removed)d, "
          "empty %(empty)d (no conversational content)." % stats)
    return 0


def cmd_search(args):
    store = Store()
    _ensure_indexed(store)
    hits = store.search(args.query, agent=args.agent, project=args.project,
                        limit=args.limit)
    if not hits:
        print("No matches.")
        store.close()
        return 0
    for i, h in enumerate(hits, 1):
        print("%2d. [%s] %s  (%s, %d msgs)"
              % (i, h["agent"], h["title"], h["date"] or "?", h["message_count"]))
        print("    id: %s" % h["id"])
        if h["project"]:
            print("    project: %s" % h["project"])
        if h["snippet"]:
            print("    … %s …" % h["snippet"])
        print()
    store.close()
    return 0


def cmd_show(args):
    store = Store()
    _ensure_indexed(store)
    session = _load_full_session(store, args.id)
    store.close()
    if session is None:
        return 1
    sys.stdout.write(render.to_markdown(session))
    return 0


def cmd_import(args):
    store = Store()
    _ensure_indexed(store)
    session = _load_full_session(store, args.id)
    if session is None:
        store.close()
        return 1
    dest_dir = Path(args.to) if args.to else (Path.cwd() / "docs" / "sessions")
    out_path = dest_dir / render.filename_for(session)
    markdown = render.to_markdown(session)
    if args.dry_run:
        print("[dry-run] would write %d bytes to %s" % (len(markdown), out_path))
        store.close()
        return 0
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    print("Imported -> %s" % out_path)
    if _maybe_has_secrets(markdown):
        print("  ⚠️  This session may contain secrets/tokens. Review before sharing.",
              file=sys.stderr)
    store.close()
    return 0


def cmd_resume(args):
    store = Store()
    _ensure_indexed(store)
    session = _load_full_session(store, args.id)
    store.close()
    if session is None:
        return 1
    sys.stdout.write(render.to_context_block(session, max_tokens=args.max_tokens))
    hint = render.native_resume_hint(session)
    if hint:
        sys.stderr.write(
            "\n(Same-agent tip: to truly re-open this session natively, try:  %s)\n"
            % hint
        )
    return 0


def _maybe_has_secrets(text: str) -> bool:
    needles = ("sk-", "ghp_", "gho_", "AKIA", "-----BEGIN", "api_key", "secret")
    low = text.lower()
    return any(n.lower() in low for n in needles)


def build_parser():
    p = argparse.ArgumentParser(prog="session-bridge", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("agents", help="list detected agents")
    sp.set_defaults(func=cmd_agents)

    sp = sub.add_parser("index", help="(re)build the search index")
    sp.add_argument("--agents", help="comma-separated subset, e.g. claude,codex")
    sp.add_argument("--force", action="store_true", help="reparse everything")
    sp.set_defaults(func=cmd_index)

    sp = sub.add_parser("search", help="search past sessions")
    sp.add_argument("query")
    sp.add_argument("--agent", help="restrict to one agent")
    sp.add_argument("--project", help="filter by project path substring")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("show", help="print a session as Markdown")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("import", help="write a session as Markdown into a project")
    sp.add_argument("id")
    sp.add_argument("--to", help="destination dir (default ./docs/sessions)")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(func=cmd_import)

    sp = sub.add_parser("resume", help="emit a context block to continue a session")
    sp.add_argument("id")
    sp.add_argument("--max-tokens", type=int, default=6000)
    sp.set_defaults(func=cmd_resume)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
