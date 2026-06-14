# session-bridge

**Search, import, and resume your coding-agent sessions — across agents.**

Claude Code, Codex, Gemini CLI and friends each keep their chat history in their
own local store, in their own format, walled off from each other. `session-bridge`
is a portable [Agent Skill](https://github.com/) that lets **any** agent:

- 🔎 **search** every agent's past sessions from one place,
- 📥 **import** a chosen session into the current project as clean Markdown, and
- ▶️ **resume** a past conversation — even one from a *different* agent — by
  injecting it back as context so you can keep going.

It is **read-only** over every agent's own data. The only things it writes are its
own index (`~/.session-bridge/`) and the Markdown files you explicitly import.

---

## Install

`session-bridge` installs like any agent skill. The easiest way is the
[`skills`](https://www.npmjs.com/package/skills) CLI, which deploys it into all of
your agents at once:

```bash
npx skills add github:cdsassj00/session-bridge
```

You'll be asked which agents to install it into (Claude Code, Codex, Cursor,
Gemini, …). That's it — no `npm install`, no global setup.

> **Manual install** (no `skills` CLI): clone this repo into your agent's skills
> folder, e.g. `~/.claude/skills/session-bridge/` (Claude Code),
> `~/.codex/skills/session-bridge/` (Codex), `~/.gemini/skills/session-bridge/`
> (Gemini). Each agent reads only its own folder.

**Runtime requirement:** Python 3.8+ (standard library only — nothing to `pip install`).

---

## Usage

Once installed, just ask your agent in natural language:

- *"Find the session where I debugged the auth flow."*
- *"Bring that Codex conversation about the parser into this project."*
- *"Let's continue the chat I had in Gemini about the data model."*

The agent runs the bundled CLI for you. You can also run it directly:

```bash
python scripts/session_bridge.py agents              # what's detected on this machine
python scripts/session_bridge.py index               # build/refresh the index (incremental)
python scripts/session_bridge.py search "auth bug"   # search across all agents
python scripts/session_bridge.py search "parser" --agent codex --limit 5
python scripts/session_bridge.py show    codex:019d   # preview as Markdown
python scripts/session_bridge.py import  codex:019d   # -> ./docs/sessions/<...>.md
python scripts/session_bridge.py resume  codex:019d   # context block to continue the chat
```

`<id>` is `<agent>:<native-id>` (e.g. `claude:1424…`); any unique substring works.

---

## How it works

```
SKILL.md                      thin instructions the agent reads
   │ calls
scripts/session_bridge.py     CLI engine
   ├── adapters/              one per agent: locate + parse -> normalized Session
   │     ├── claude.py        ~/.claude/projects/**/*.jsonl
   │     ├── codex.py         ~/.codex/sessions/**/rollout-*.jsonl
   │     └── gemini.py        ~/.gemini/tmp/**/chats/session-*.json
   ├── store.py               SQLite (FTS5) index + search
   ├── render.py              Markdown export + resume context block
   └── model.py               normalized Session / Message
   │ reads (READ-ONLY)
[ ~/.claude  ·  ~/.codex  ·  ~/.gemini  · … ]   never modified

writes only:  ~/.session-bridge/index.sqlite   and   ./docs/sessions/*.md (on import)
```

- **Search** uses SQLite FTS5 (BM25 + recency) when available, falling back to a
  plain `LIKE` scan otherwise. No embeddings, no external services.
- **Resume** is *context injection*: the past conversation is summarized into a
  compact block and handed to the current agent to continue from — which is why it
  works across agents. For same-agent sessions it also surfaces the native resume
  command.

---

## Supported agents (v1)

| Agent | Store | Status |
|-------|-------|--------|
| Claude Code | `~/.claude/projects/**/*.jsonl` | ✅ |
| Codex | `~/.codex/sessions/**/rollout-*.jsonl` | ✅ |
| Gemini CLI | `~/.gemini/tmp/**/chats/session-*.json` | ✅ |
| Copilot CLI, Cursor (SQLite) | — | planned |

### Adding an agent

Create `scripts/adapters/<agent>.py` with an `Adapter` subclass implementing
`root()`, `discover()`, and `parse()`, then register it in
`scripts/adapters/__init__.py`. That's the only change needed. PRs welcome.

---

## Privacy & safety

- **Read-only:** other agents' session files are never written, moved, or deleted.
- Sessions can contain secrets/tokens. `import` warns when it detects likely
  secrets; review imported Markdown before sharing or committing it.
- Everything runs locally; nothing is uploaded anywhere.

---

## Development

```bash
python -m unittest discover -s tests -v
```

Tests use synthetic fixtures and need no real session data.

## License

MIT — see [LICENSE](LICENSE).
