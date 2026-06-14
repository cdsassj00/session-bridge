"""Adapter registry.

To support a new agent: add an adapter module and register its class here.
That is the ONLY change needed for new agents.
"""
from pathlib import Path
from typing import List, Optional

from adapters.base import Adapter
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter
from adapters.gemini import GeminiAdapter

ALL_ADAPTERS = [ClaudeAdapter, CodexAdapter, GeminiAdapter]


def get_adapters(names=None, home: Optional[Path] = None) -> List[Adapter]:
    """Instantiate adapters, optionally filtered by name, available ones only."""
    wanted = set(names) if names else None
    out = []
    for cls in ALL_ADAPTERS:
        if wanted and cls.name not in wanted:
            continue
        out.append(cls(home=home))
    return out


def adapter_for(agent: str, home: Optional[Path] = None) -> Optional[Adapter]:
    for cls in ALL_ADAPTERS:
        if cls.name == agent:
            return cls(home=home)
    return None
