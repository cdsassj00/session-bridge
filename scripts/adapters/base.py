"""Adapter interface. One subclass per coding agent.

An adapter knows three things about one agent:
  1. WHERE that agent stores sessions (and whether it exists on this machine),
  2. HOW to enumerate session files,
  3. HOW to parse one file into a normalized Session.

Adapters are strictly READ-ONLY. They must never write, move, or delete
anything inside an agent's own store.
"""
from pathlib import Path
from typing import Iterator, Optional

from model import Session


class Adapter:
    name = "base"

    def __init__(self, home: Optional[Path] = None):
        # `home` is injectable so tests can point at a fake HOME.
        self.home = Path(home) if home else Path.home()

    # --- location -----------------------------------------------------------
    def root(self) -> Path:
        """Directory under which this agent keeps its sessions."""
        raise NotImplementedError

    def is_available(self) -> bool:
        try:
            return self.root().is_dir()
        except OSError:
            return False

    # --- enumeration --------------------------------------------------------
    def discover(self) -> Iterator[Path]:
        """Yield absolute paths of session files."""
        raise NotImplementedError

    # --- parsing ------------------------------------------------------------
    def parse(self, path: Path) -> Optional[Session]:
        """Parse one session file into a Session, or None if unreadable/empty."""
        raise NotImplementedError


# --- small shared helpers ---------------------------------------------------

def clip(text: str, limit: int = 80) -> str:
    text = " ".join((text or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


def looks_like_system_block(text: str) -> bool:
    """Heuristic: injected wrappers / CLI banners we don't want as conversation."""
    t = (text or "").lstrip()
    if not t:
        return True
    markers = (
        "<local-command", "<command-name", "<command-message", "<command-args",
        "<bash-input", "<bash-stdout", "<bash-stderr", "<system-reminder",
        "<environment_context", "<permissions", "<user_instructions", "<INSTRUCTIONS>",
    )
    if t.startswith(markers):
        return True
    # CLI startup banners / injected agent instructions captured as turns.
    flat = " ".join(t.split())
    banners = (
        "# AGENTS.md instructions", "You are Codex", "You are a coding agent",
        "Tip: New Use",
    )
    if flat.startswith(banners):
        return True
    if "Skipped loading" in flat and "due to invalid SKILL.md" in flat:
        return True
    return False
