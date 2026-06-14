"""Normalized session/message data model shared by all adapters.

Every adapter converts its agent's native format into these two dataclasses,
so the rest of the engine (index, search, export, resume) is agent-agnostic.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Message:
    role: str                 # user | assistant | system | tool
    text: str                 # human-readable, flattened text
    ts: Optional[str] = None  # ISO8601 timestamp if available


@dataclass
class Session:
    id: str                       # stable id: "<agent>:<native_id>"
    agent: str                    # claude | codex | gemini | ...
    title: str
    project: Optional[str]        # cwd / project the session belonged to
    started_at: Optional[str]     # ISO8601
    ended_at: Optional[str]       # ISO8601
    message_count: int
    source_path: str              # absolute path to the original file
    messages: List[Message] = field(default_factory=list)

    def body_text(self) -> str:
        """Concatenated searchable text (title + all message text)."""
        parts = [self.title or ""]
        parts.extend(m.text for m in self.messages if m.text)
        return "\n".join(parts)

    def date(self) -> str:
        """Best-effort YYYY-MM-DD for display / filenames."""
        stamp = self.started_at or self.ended_at or ""
        return stamp[:10] if stamp else ""
