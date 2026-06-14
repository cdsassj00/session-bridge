---
name: session-bridge
description: Search, import, and resume past coding-agent sessions across DIFFERENT agents. Use when the user wants to find a previous conversation from Claude Code, Codex, or Gemini CLI ("find the chat where we discussed X", "what did I do about the auth bug"), pull an old session into the current project as a Markdown file ("bring that session here", "save that conversation as a doc"), or continue a conversation that happened in another agent or another session ("resume the Codex session about the parser", "continue where we left off in Gemini"). Works read-only across every agent's local session store.
---

# session-bridge

Your coding agents (Claude Code, Codex, Gemini CLI, …) each store their chat
sessions locally, in different formats, isolated from one another. **session-bridge**
lets *any* agent search across *all* of those stores, import a chosen session
into the current project as clean Markdown, and resume a past conversation by
injecting it back as context — even across agents (e.g. continue a Codex chat
inside Claude).

It is strictly **read-only** over other agents' data. The only things it writes
are its own search index (`~/.session-bridge/`) and Markdown files you explicitly
import.

## How to run it

The engine is a bundled, dependency-free Python CLI (stdlib only, Python 3.8+).
From this skill's directory, call:

```
python scripts/session_bridge.py <command> [args]
```

(If you are unsure of the absolute path, it is `<this-skill-dir>/scripts/session_bridge.py`.)

## Commands

| Goal | Command |
|------|---------|
| See which agents are detected | `python scripts/session_bridge.py agents` |
| Build/refresh the search index | `python scripts/session_bridge.py index` |
| Search past sessions | `python scripts/session_bridge.py search "<query>" [--agent A] [--project P] [--limit N]` |
| Preview a session as Markdown | `python scripts/session_bridge.py show <id>` |
| Import a session into this project | `python scripts/session_bridge.py import <id> [--to DIR]` |
| Resume / continue a session | `python scripts/session_bridge.py resume <id>` |

`<id>` looks like `claude:1424…`, `codex:019d…`, or `gemini:g1`. You can pass a
unique substring of the id and it will be resolved.

## Typical workflows

**"Find that conversation about X and bring it here."**
1. `search "X"` → read the ranked hits, pick the right `id`.
2. `import <id>` → writes `./docs/sessions/<date>-<agent>-<title>.md` into the
   current project. Tell the user the path.

**"Continue the session I had in another agent."**
1. `search "<topic>" --agent codex` (or whichever) → find the `id`.
2. `resume <id>` → emits a context block. Read it, briefly confirm you've
   absorbed the prior conversation, then continue with the user from there.
   (If it's the same agent you're running in, the command also prints the native
   resume command on stderr as a convenience.)

**First run on a machine:** the index builds automatically on first search, but
you can run `index` explicitly. Re-running `index` is incremental (only changed
sessions are re-parsed).

## Notes

- **Read-only & safe:** other agents' session files are never modified, moved, or
  deleted.
- **Privacy:** sessions can contain secrets/tokens. `import` warns if it detects
  likely secrets; review imported files before sharing or committing.
- **Portability:** session store locations are auto-detected from the user's home
  directory (Windows / macOS / Linux). Agents that aren't installed are skipped.
- **Extensible:** support for a new agent = one new file in `scripts/adapters/`.
  v1 ships Claude Code, Codex, and Gemini CLI.
