"""Gemini CLI adapter.

Store layout:  ~/.gemini/tmp/<project-hash>/chats/session-<ts>-<id>.json
The file is a single JSON object:
  {sessionId, projectHash, startTime, lastUpdated, messages: [
      {id, timestamp, type, content}, ...
  ]}
`type` is "user" for the human; anything else is treated as the assistant.
`content` is usually a string, occasionally a list of parts.
"""
import json
from pathlib import Path
from typing import Iterator, Optional

from model import Session, Message
from adapters.base import Adapter, clip, looks_like_system_block


class GeminiAdapter(Adapter):
    name = "gemini"

    def root(self) -> Path:
        return self.home / ".gemini" / "tmp"

    def discover(self) -> Iterator[Path]:
        if not self.is_available():
            return
        for chats in self.root().glob("*/chats"):
            yield from chats.glob("session-*.json")

    def parse(self, path: Path) -> Optional[Session]:
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None

        raw = data.get("messages") or []
        messages = []
        for m in raw:
            if not isinstance(m, dict):
                continue
            text = _as_text(m.get("content"))
            if not text or looks_like_system_block(text):
                continue
            role = "user" if m.get("type") == "user" else "assistant"
            messages.append(Message(role=role, text=text, ts=m.get("timestamp")))

        if not messages:
            return None

        session_id = data.get("sessionId") or path.stem
        first_user = next((m.text for m in messages if m.role == "user"), "")
        title = clip(first_user, 80) or path.stem

        return Session(
            id="gemini:" + session_id,
            agent=self.name,
            title=title,
            project=data.get("projectHash"),
            started_at=data.get("startTime"),
            ended_at=data.get("lastUpdated"),
            message_count=len(messages),
            source_path=str(path),
            messages=messages,
        )


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        out = []
        for part in value:
            if isinstance(part, dict):
                out.append(part.get("text") or part.get("content") or "")
            else:
                out.append(str(part))
        return "\n".join(p for p in out if p).strip()
    if isinstance(value, dict):
        return (value.get("text") or value.get("content") or "").strip()
    return str(value).strip()
