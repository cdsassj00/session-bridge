"""Self-contained tests using synthetic fixtures (no real session data needed).

Run with:  python -m unittest discover -s tests
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from adapters import adapter_for                 # noqa: E402
from adapters.claude import ClaudeAdapter        # noqa: E402
from adapters.codex import CodexAdapter          # noqa: E402
from adapters.gemini import GeminiAdapter        # noqa: E402
from store import Store                          # noqa: E402
import render                                    # noqa: E402


def build_fake_home(base: Path):
    """Create a minimal fake HOME with one session per agent."""
    # --- Claude ---
    cdir = base / ".claude" / "projects" / "projA"
    cdir.mkdir(parents=True)
    with (cdir / "sess1.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "user", "sessionId": "abc",
                             "cwd": "/home/me/projA", "timestamp": "2026-01-01T00:00:00Z",
                             "message": {"role": "user",
                                         "content": "How do I reverse a list in Python?"}}) + "\n")
        fh.write(json.dumps({
            "type": "assistant", "timestamp": "2026-01-01T00:00:05Z",
            "message": {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "x"},
                {"type": "text", "text": "Use reversed() or [::-1]."},
            ]},
        }) + "\n")
        fh.write(json.dumps({
            "type": "user", "isMeta": True,
            "message": {"role": "user",
                        "content": "<local-command-caveat>noise</local-command-caveat>"},
        }) + "\n")
        fh.write(json.dumps({"type": "ai-title", "title": "Reversing a list"}) + "\n")

    # --- Codex ---
    xdir = base / ".codex" / "sessions" / "2026" / "01" / "02"
    xdir.mkdir(parents=True)
    with (xdir / "rollout-2026-01-02T00-00-00-uuid1.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"timestamp": "2026-01-02T00:00:00Z", "type": "session_meta",
                             "payload": {"id": "xyz", "cwd": "/home/me/projB"}}) + "\n")
        fh.write(json.dumps({"timestamp": "2026-01-02T00:00:01Z", "type": "event_msg",
                             "payload": {"type": "user_message",
                                         "message": "What is a closure?"}}) + "\n")
        fh.write(json.dumps({"timestamp": "2026-01-02T00:00:02Z", "type": "event_msg",
                             "payload": {"type": "agent_message",
                                         "message": "A closure captures variables."}}) + "\n")
        fh.write(json.dumps({"timestamp": "2026-01-02T00:00:03Z", "type": "response_item",
                             "payload": {"type": "function_call", "name": "shell"}}) + "\n")

    # --- Gemini ---
    gdir = base / ".gemini" / "tmp" / "hashX" / "chats"
    gdir.mkdir(parents=True)
    (gdir / "session-2026-01-03T00-00-g1.json").write_text(json.dumps({
        "sessionId": "g1", "projectHash": "hashX",
        "startTime": "2026-01-03T00:00:00Z", "lastUpdated": "2026-01-03T00:05:00Z",
        "messages": [
            {"id": "1", "timestamp": "2026-01-03T00:00:00Z", "type": "user",
             "content": "Explain recursion"},
            {"id": "2", "timestamp": "2026-01-03T00:00:10Z", "type": "gemini",
             "content": "Recursion is a function calling itself."},
        ],
    }), encoding="utf-8")


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        build_fake_home(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def test_claude(self):
        ad = ClaudeAdapter(home=self.home)
        self.assertTrue(ad.is_available())
        sessions = [ad.parse(p) for p in ad.discover()]
        sessions = [s for s in sessions if s]
        self.assertEqual(len(sessions), 1)
        s = sessions[0]
        self.assertEqual(s.agent, "claude")
        self.assertEqual(s.id, "claude:abc")
        self.assertEqual(s.title, "Reversing a list")     # from ai-title
        self.assertEqual(s.message_count, 2)              # meta line skipped
        self.assertEqual(s.messages[0].role, "user")
        self.assertIn("reversed()", s.messages[1].text)   # thinking dropped, text kept
        self.assertEqual(s.project, "/home/me/projA")

    def test_codex(self):
        ad = CodexAdapter(home=self.home)
        sessions = [s for s in (ad.parse(p) for p in ad.discover()) if s]
        self.assertEqual(len(sessions), 1)
        s = sessions[0]
        self.assertEqual(s.agent, "codex")
        self.assertEqual(s.message_count, 2)              # function_call skipped
        self.assertEqual(s.title, "What is a closure?")
        self.assertEqual(s.project, "/home/me/projB")
        self.assertEqual([m.role for m in s.messages], ["user", "assistant"])

    def test_gemini(self):
        ad = GeminiAdapter(home=self.home)
        sessions = [s for s in (ad.parse(p) for p in ad.discover()) if s]
        self.assertEqual(len(sessions), 1)
        s = sessions[0]
        self.assertEqual(s.id, "gemini:g1")
        self.assertEqual(s.message_count, 2)
        self.assertEqual([m.role for m in s.messages], ["user", "assistant"])

    def test_missing_agent_is_skipped(self):
        empty = Path(self.tmp.name) / "nope"
        empty.mkdir()
        ad = ClaudeAdapter(home=empty)
        self.assertFalse(ad.is_available())
        self.assertEqual(list(ad.discover()), [])


class StoreAndRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        build_fake_home(self.home)
        os.environ["SESSION_BRIDGE_HOME"] = str(self.home / ".sbdata")
        self.store = Store()

    def tearDown(self):
        self.store.close()
        os.environ.pop("SESSION_BRIDGE_HOME", None)
        self.tmp.cleanup()

    def test_index_and_search(self):
        stats = self.store.index(home=self.home)
        self.assertEqual(stats["indexed"], 3)            # claude+codex+gemini
        self.assertEqual(self.store.count(), 3)

        hits = self.store.search("closure")
        self.assertTrue(any(h["agent"] == "codex" for h in hits))

        hits = self.store.search("recursion", agent="gemini")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["id"], "gemini:g1")

    def test_incremental_skip(self):
        self.store.index(home=self.home)
        stats2 = self.store.index(home=self.home)
        self.assertEqual(stats2["indexed"], 0)
        self.assertEqual(stats2["skipped"], 3)

    def test_markdown_is_yaml_safe(self):
        ad = adapter_for("codex", home=self.home)
        session = next(s for s in (ad.parse(p) for p in ad.discover()) if s)
        md = render.to_markdown(session)
        self.assertIn("---", md)
        self.assertIn("source_agent: codex", md)
        # A Windows-style path must be single-quoted so backslashes stay literal
        # and are not parsed as YAML escape sequences (e.g. C:\Users -> \U...).
        session.source_path = r"C:\Users\me\x.jsonl"
        sample = render.to_markdown(session)
        self.assertIn(r"original_path: 'C:\Users\me\x.jsonl'", sample)
        self.assertNotIn('"C:\\', sample)

    def test_resume_block(self):
        ad = adapter_for("gemini", home=self.home)
        session = next(s for s in (ad.parse(p) for p in ad.discover()) if s)
        block = render.to_context_block(session, max_tokens=5000)
        self.assertIn("RESUMED CONVERSATION", block)
        self.assertIn("Recursion", block)

    def test_filename_slug(self):
        ad = adapter_for("gemini", home=self.home)
        session = next(s for s in (ad.parse(p) for p in ad.discover()) if s)
        name = render.filename_for(session)
        self.assertTrue(name.endswith(".md"))
        self.assertIn("gemini", name)


if __name__ == "__main__":
    unittest.main()
