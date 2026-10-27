"""SQLite-backed store for scenes (a scene is one capture: its processing job and resulting model)."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

# queued -> running -> done | failed | cancelled ; running scenes found at startup become `interrupted`.
ACTIVE_STATUSES = ("queued", "running")
FINAL_STATUSES = ("done", "failed", "cancelled", "interrupted")

_JSON_FIELDS = ("artifacts", "stats", "stage_times")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scenes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    preset TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT,
    stage_started_at REAL,
    stage_progress REAL NOT NULL DEFAULT 0,
    progress REAL NOT NULL DEFAULT 0,
    error TEXT,
    source_filename TEXT,
    created_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL,
    artifacts TEXT NOT NULL DEFAULT '{}',
    stats TEXT NOT NULL DEFAULT '{}',
    stage_times TEXT NOT NULL DEFAULT '{}'
);
"""


class SceneStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            columns = {row[1] for row in self._conn.execute("PRAGMA table_info(scenes)")}
            if "stage_started_at" not in columns:  # databases created before this column existed
                self._conn.execute("ALTER TABLE scenes ADD COLUMN stage_started_at REAL")
            self._conn.commit()

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        scene = dict(row)
        for key in _JSON_FIELDS:
            scene[key] = json.loads(scene[key] or "{}")
        return scene

    def create(self, name: str, preset: str, source_filename: str | None = None,
               status: str = "queued", scene_id: str | None = None) -> dict[str, Any]:
        scene_id = scene_id or uuid.uuid4().hex[:12]
        with self._lock:
            self._conn.execute(
                "INSERT INTO scenes (id, name, preset, status, source_filename, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (scene_id, name, preset, status, source_filename, time.time()),
            )
            self._conn.commit()
        return self.get(scene_id)

    def get(self, scene_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,)).fetchone()
        return self._decode(row)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM scenes ORDER BY created_at DESC").fetchall()
        return [self._decode(r) for r in rows]

    def update(self, scene_id: str, **fields: Any) -> dict[str, Any] | None:
        if fields:
            for key in _JSON_FIELDS:
                if key in fields:
                    fields[key] = json.dumps(fields[key])
            assignments = ", ".join(f"{key} = ?" for key in fields)
            with self._lock:
                self._conn.execute(f"UPDATE scenes SET {assignments} WHERE id = ?", (*fields.values(), scene_id))
                self._conn.commit()
        return self.get(scene_id)

    def delete(self, scene_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM scenes WHERE id = ?", (scene_id,))
            self._conn.commit()

    def next_queued(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM scenes WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
        return self._decode(row)

    def mark_interrupted(self) -> int:
        """Called at startup: anything still `running` or `uploading` died with the previous server process."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE scenes SET status = 'interrupted', error = 'Server stopped while this scene was processing.', "
                "finished_at = ? WHERE status = 'running'",
                (time.time(),),
            )
            self._conn.execute(
                "UPDATE scenes SET status = 'failed', error = 'The upload did not complete.', finished_at = ? "
                "WHERE status = 'uploading'",
                (time.time(),),
            )
            self._conn.commit()
        return cur.rowcount
