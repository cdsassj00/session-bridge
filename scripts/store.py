"""Central index + search, backed by SQLite.

The ONLY place session-bridge writes to (besides an explicit import target):
  ~/.session-bridge/index.sqlite

Uses FTS5 full-text search when the local SQLite build supports it, and
transparently falls back to LIKE-based search otherwise.
"""
import os
import sqlite3
from pathlib import Path
from typing import List, Optional

from adapters import get_adapters


def data_dir() -> Path:
    override = os.environ.get("SESSION_BRIDGE_HOME")
    base = Path(override) if override else (Path.home() / ".session-bridge")
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / "index.sqlite"


def _fts5_available(con: sqlite3.Connection) -> bool:
    try:
        con.execute("CREATE VIRTUAL TABLE temp.__fts_probe USING fts5(x)")
        con.execute("DROP TABLE temp.__fts_probe")
        return True
    except sqlite3.OperationalError:
        return False


class Store:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else db_path()
        self.con = sqlite3.connect(str(self.path))
        self.con.row_factory = sqlite3.Row
        self.fts = _fts5_available(self.con)
        self._init_schema()

    def _init_schema(self):
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                agent TEXT,
                title TEXT,
                project TEXT,
                started_at TEXT,
                ended_at TEXT,
                message_count INTEGER,
                source_path TEXT,
                mtime REAL,
                body TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent);
            """
        )
        if self.fts:
            self.con.executescript(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts
                USING fts5(id UNINDEXED, title, body);
                """
            )
        self.con.commit()

    # --- indexing -----------------------------------------------------------
    def index(self, agents=None, home=None, force=False) -> dict:
        stats = {"indexed": 0, "skipped": 0, "removed": 0, "empty": 0}
        seen_paths = {}
        for adapter in get_adapters(agents, home=home):
            if not adapter.is_available():
                continue
            for path in adapter.discover():
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                seen_paths[str(path)] = mtime
                if not force and self._is_current(str(path), mtime):
                    stats["skipped"] += 1
                    continue
                session = adapter.parse(path)
                if session is None:
                    stats["empty"] += 1
                    continue
                self._upsert(session, mtime)
                stats["indexed"] += 1
        self.con.commit()
        return stats

    def _is_current(self, source_path: str, mtime: float) -> bool:
        row = self.con.execute(
            "SELECT mtime FROM sessions WHERE source_path = ?", (source_path,)
        ).fetchone()
        return row is not None and row["mtime"] == mtime

    def _upsert(self, session, mtime: float):
        body = session.body_text()
        self.con.execute(
            """
            INSERT INTO sessions
                (id, agent, title, project, started_at, ended_at,
                 message_count, source_path, mtime, body)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                agent=excluded.agent, title=excluded.title, project=excluded.project,
                started_at=excluded.started_at, ended_at=excluded.ended_at,
                message_count=excluded.message_count, source_path=excluded.source_path,
                mtime=excluded.mtime, body=excluded.body
            """,
            (session.id, session.agent, session.title, session.project,
             session.started_at, session.ended_at, session.message_count,
             session.source_path, mtime, body),
        )
        if self.fts:
            self.con.execute("DELETE FROM sessions_fts WHERE id = ?", (session.id,))
            self.con.execute(
                "INSERT INTO sessions_fts (id, title, body) VALUES (?,?,?)",
                (session.id, session.title, body),
            )

    def count(self) -> int:
        return self.con.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]

    # --- search -------------------------------------------------------------
    def search(self, query: str, agent=None, project=None, limit=20) -> List[dict]:
        if self.fts and query.strip():
            rows = self._search_fts(query, agent, project, limit)
        else:
            rows = self._search_like(query, agent, project, limit)
        return rows

    def _filters(self, agent, project):
        clauses, params = [], []
        if agent:
            clauses.append("s.agent = ?")
            params.append(agent)
        if project:
            clauses.append("s.project LIKE ?")
            params.append("%" + project + "%")
        return clauses, params

    def _search_fts(self, query, agent, project, limit):
        clauses, params = self._filters(agent, project)
        where = " AND ".join(["sessions_fts MATCH ?"] + clauses)
        sql = (
            "SELECT s.*, snippet(sessions_fts, 2, '[', ']', ' … ', 12) AS snippet "
            "FROM sessions_fts JOIN sessions s ON s.id = sessions_fts.id "
            "WHERE " + where + " "
            "ORDER BY bm25(sessions_fts) ASC, s.ended_at DESC LIMIT ?"
        )
        try:
            rows = self.con.execute(sql, [_fts_query(query)] + params + [limit]).fetchall()
        except sqlite3.OperationalError:
            return self._search_like(query, agent, project, limit)
        return [self._row_to_hit(r, dict(r).get("snippet")) for r in rows]

    def _search_like(self, query, agent, project, limit):
        clauses, params = self._filters(agent, project)
        if query.strip():
            clauses.append("(s.body LIKE ? OR s.title LIKE ?)")
            params.extend(["%" + query + "%", "%" + query + "%"])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = ("SELECT s.* FROM sessions s" + where +
               " ORDER BY s.ended_at DESC LIMIT ?")
        rows = self.con.execute(sql, params + [limit]).fetchall()
        return [self._row_to_hit(r, _make_snippet(r["body"], query)) for r in rows]

    def _row_to_hit(self, row, snippet):
        return {
            "id": row["id"],
            "agent": row["agent"],
            "title": row["title"],
            "project": row["project"],
            "date": (row["started_at"] or row["ended_at"] or "")[:10],
            "message_count": row["message_count"],
            "source_path": row["source_path"],
            "snippet": " ".join((snippet or "").split())[:160],
        }

    def get(self, session_id: str) -> Optional[dict]:
        row = self.con.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    def find_by_suffix(self, partial: str) -> List[dict]:
        rows = self.con.execute(
            "SELECT * FROM sessions WHERE id LIKE ? ORDER BY ended_at DESC LIMIT 5",
            ("%" + partial + "%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.con.close()


def _fts_query(query: str) -> str:
    # Make a safe FTS5 query: OR the tokens so partial matches still rank.
    tokens = [t for t in _tokenize(query) if t]
    if not tokens:
        return '""'
    return " OR ".join('"%s"' % t.replace('"', '') for t in tokens)


def _tokenize(text: str):
    cur = []
    for ch in text:
        if ch.isalnum() or ord(ch) > 127:  # keep CJK and word chars
            cur.append(ch)
        else:
            if cur:
                yield "".join(cur)
                cur = []
    if cur:
        yield "".join(cur)


def _make_snippet(body: str, query: str) -> str:
    if not body:
        return ""
    if query.strip():
        low = body.lower()
        idx = low.find(query.lower().split()[0]) if query.split() else -1
        if idx >= 0:
            start = max(0, idx - 40)
            return body[start:start + 160]
    return body[:160]
