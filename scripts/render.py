"""Render a parsed Session into:
  - a clean Markdown document (for `import`)
  - a compact context block (for `resume` / continue-the-conversation)
"""
import re
from model import Session

ROLE_LABEL = {
    "user": "👤 User",
    "assistant": "🤖 Assistant",
    "system": "⚙️ System",
    "tool": "🔧 Tool",
}

# Native resume hints per agent (best-effort convenience for same-agent resume).
NATIVE_RESUME = {
    "claude": "claude --resume {nid}",
    "codex": "codex resume {nid}",
}


def slugify(text: str, limit: int = 50) -> str:
    text = (text or "").strip().lower()
    # keep word chars and CJK, turn the rest into hyphens
    text = re.sub(r"[^\w가-힣]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:limit] or "session"


def filename_for(session: Session) -> str:
    date = session.date() or "undated"
    short = session.id.split(":")[-1][:8]
    return "%s-%s-%s-%s.md" % (date, session.agent, slugify(session.title), short)


def _yaml_escape(value) -> str:
    # Single-quoted YAML so Windows backslash paths (C:\Users -> \U ...) are
    # NOT treated as escape sequences. Inner single quotes are doubled.
    if value is None:
        return "''"
    s = " ".join(str(value).split())  # collapse newlines for safe frontmatter
    return "'%s'" % s.replace("'", "''")


def to_markdown(session: Session) -> str:
    fm = [
        "---",
        "source_agent: %s" % session.agent,
        "source_id: %s" % _yaml_escape(session.id),
        "original_path: %s" % _yaml_escape(session.source_path),
        "title: %s" % _yaml_escape(session.title),
        "project: %s" % _yaml_escape(session.project),
        "started_at: %s" % _yaml_escape(session.started_at),
        "ended_at: %s" % _yaml_escape(session.ended_at),
        "message_count: %d" % session.message_count,
        "imported_by: session-bridge",
        "---",
        "",
        "# %s" % (session.title or session.id),
        "",
        "> Imported from a **%s** session by session-bridge. "
        "Original file is referenced in `original_path` above." % session.agent,
        "",
    ]
    body = []
    for m in session.messages:
        label = ROLE_LABEL.get(m.role, m.role)
        body.append("## %s" % label)
        body.append("")
        body.append(m.text.strip())
        body.append("")
    return "\n".join(fm + body).rstrip() + "\n"


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def to_context_block(session: Session, max_tokens: int = 6000) -> str:
    """Compact block meant to be pasted/injected into a live conversation so the
    current agent can continue the thread. Keeps the most recent messages
    verbatim within the token budget; older ones are noted as truncated."""
    header = [
        "===== RESUMED CONVERSATION (via session-bridge) =====",
        "Source: %s session  |  Date: %s  |  Project: %s"
        % (session.agent, session.date() or "?", session.project or "?"),
        "Title: %s" % session.title,
        "Original: %s" % session.source_path,
        "",
        "Below is the prior conversation. Treat it as earlier context, then "
        "continue with the user from where it left off.",
        "",
    ]
    rendered = []
    used = estimate_tokens("\n".join(header))
    truncated = 0
    for m in reversed(session.messages):
        label = ROLE_LABEL.get(m.role, m.role)
        chunk = "%s: %s" % (label, m.text.strip())
        cost = estimate_tokens(chunk)
        if used + cost > max_tokens and rendered:
            truncated += 1
            continue
        rendered.append(chunk)
        used += cost
    rendered.reverse()

    note = []
    if truncated:
        note = ["[... %d earlier message(s) truncated to fit budget ...]" % truncated, ""]

    footer = ["", "===== END OF RESUMED CONVERSATION ====="]
    return "\n".join(header + note + rendered + footer) + "\n"


def native_resume_hint(session: Session) -> str:
    tmpl = NATIVE_RESUME.get(session.agent)
    if not tmpl:
        return ""
    nid = session.id.split(":", 1)[-1]
    return tmpl.format(nid=nid)
