"""Codex (OpenAI) adapter.

Store layout:  ~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl
Each line is {timestamp, type, payload}. We use the clean human-readable turns:
  - event_msg / user_message   -> user      (payload.message)
  - event_msg / agent_message  -> assistant (payload.message)
  - session_meta               -> cwd / id
Function calls, reasoning, token_count, etc. are tool/plumbing -> skipped.
"""
import json
from pathlib import Path
from typing import Iterator, Optional

from model import Session, Message
from adapters.base import Adapter, clip, looks_like_system_block


class CodexAdapter(Adapter):
    name = "codex"

    def root(self) -> Path:
        return self.home / ".codex" / "sessions"

    def discover(self) -> Iterator[Path]:
        if not self.is_available():
            return
        yield from self.root().rglob("rollout-*.jsonl")

    @staticmethod
    def _add(bucket, role, raw, ts):
        text = _as_text(raw)
        if text and not looks_like_system_block(text):
            bucket.append(Message(role=role, text=text, ts=ts))

    def parse(self, path: Path) -> Optional[Session]:
        session_id = _id_from_name(path.stem)
        cwd = None
        primary = []     # clean event-stream turns (preferred)
        fallback = []    # older response_item/message turns
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

                    ttype = rec.get("type")
                    payload = rec.get("payload") or {}
                    if not isinstance(payload, dict):
                        continue
                    ptype = payload.get("type")
                    ts = rec.get("timestamp")
                    if ts:
                        timestamps.append(ts)

                    if ttype == "session_meta":
                        cwd = cwd or payload.get("cwd") or payload.get("cwd_path")
                        session_id = payload.get("id") or session_id
                        continue

                    # Preferred: clean human-readable event stream.
                    if ttype == "event_msg" and ptype == "user_message":
                        self._add(primary, "user", payload.get("message"), ts)
                    elif ttype == "event_msg" and ptype == "agent_message":
                        self._add(primary, "assistant", payload.get("message"), ts)
                    # Fallback for older sessions without event_msg turns.
                    elif ttype == "response_item" and ptype == "message":
                        role = payload.get("role")
                        if role in ("user", "assistant"):
                            self._add(fallback, role, payload.get("content"), ts)
        except OSError:
            return None

        messages = primary or fallback
        if not messages:
            return None

        first_user = next((m.text for m in messages if m.role == "user"), "")
        title = clip(first_user, 80) or path.stem

        return Session(
            id="codex:" + session_id,
            agent=self.name,
            title=title,
            project=cwd,
            started_at=timestamps[0] if timestamps else None,
            ended_at=timestamps[-1] if timestamps else None,
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
        for b in value:
            if isinstance(b, dict):
                out.append(b.get("text") or b.get("content") or "")
            else:
                out.append(str(b))
        return "\n".join(p for p in out if p).strip()
    return str(value).strip()


def _id_from_name(stem: str) -> str:
    # rollout-2026-06-14T19-10-53-019ec59c-... -> keep the trailing uuid-ish part
    parts = stem.split("-")
    return "-".join(parts[-5:]) if len(parts) >= 5 else stem
