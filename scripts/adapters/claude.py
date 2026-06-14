"""Claude Code adapter.

Store layout:  ~/.claude/projects/<encoded-project>/<session-uuid>.jsonl
Each line is one JSON record. Relevant record `type`s:
  - "user"      : message.content is a str OR a list of content blocks
  - "assistant" : message.content is a list of blocks (text / thinking / tool_use)
  - "ai-title"  : a generated short title for the session
Records with isMeta/isSidechain or system wrappers are skipped.
"""
import json
from pathlib import Path
from typing import Iterator, Optional

from model import Session, Message
from adapters.base import Adapter, clip, looks_like_system_block


class ClaudeAdapter(Adapter):
    name = "claude"

    def root(self) -> Path:
        return self.home / ".claude" / "projects"

    def discover(self) -> Iterator[Path]:
        if not self.is_available():
            return
        yield from self.root().rglob("*.jsonl")

    def parse(self, path: Path) -> Optional[Session]:
        session_id = path.stem
        cwd = None
        title = None
        messages = []
        timestamps = []

        try:
            with path.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    rtype = rec.get("type")
                    if rec.get("sessionId"):
                        session_id = rec["sessionId"]
                    if rec.get("cwd") and not cwd:
                        cwd = rec["cwd"]

                    if rtype == "ai-title":
                        title = (
                            rec.get("title")
                            or rec.get("aiTitle")
                            or (rec.get("message") or {}).get("content")
                            or title
                        )
                        continue

                    if rtype not in ("user", "assistant"):
                        continue
                    if rec.get("isMeta") or rec.get("isSidechain"):
                        continue

                    msg = rec.get("message") or {}
                    role = msg.get("role", rtype)
                    text = _extract_text(msg.get("content"))
                    if not text or looks_like_system_block(text):
                        continue

                    ts = rec.get("timestamp")
                    if ts:
                        timestamps.append(ts)
                    messages.append(Message(role=role, text=text, ts=ts))
        except OSError:
            return None

        if not messages:
            return None

        if not title:
            first_user = next((m.text for m in messages if m.role == "user"), "")
            title = clip(first_user, 80) or path.stem

        return Session(
            id="claude:" + session_id,
            agent=self.name,
            title=title,
            project=cwd,
            started_at=timestamps[0] if timestamps else None,
            ended_at=timestamps[-1] if timestamps else None,
            message_count=len(messages),
            source_path=str(path),
            messages=messages,
        )


def _extract_text(content) -> str:
    """Flatten Claude's str|list message content into readable text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return str(content).strip()

    out = []
    for block in content:
        if not isinstance(block, dict):
            out.append(str(block))
            continue
        btype = block.get("type")
        if btype == "text":
            out.append(block.get("text", ""))
        elif btype == "tool_use":
            out.append("[tool: %s]" % block.get("name", "?"))
        elif btype == "tool_result":
            inner = block.get("content")
            if isinstance(inner, list):
                txt = " ".join(
                    b.get("text", "") for b in inner if isinstance(b, dict)
                ).strip()
                out.append("[tool result] " + clip(txt, 200) if txt else "[tool result]")
            elif isinstance(inner, str):
                out.append("[tool result] " + clip(inner, 200))
            else:
                out.append("[tool result]")
        # thinking blocks are intentionally dropped for readability
    return "\n".join(p for p in out if p).strip()
