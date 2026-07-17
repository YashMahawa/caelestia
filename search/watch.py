#!/usr/bin/python3
"""Tiny inotify front-end: queue real changes and wake the bounded worker."""

import json
import fnmatch
import mimetypes
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import pyinotify

HOME = Path.home()
CONFIG = HOME / ".config/caelestia/semantic-search.json"
DB = HOME / ".local/share/caelestia-search/index.sqlite3"
CFG = json.loads(CONFIG.read_text())
EXCLUDED_DIRECTORIES = set(CFG["exclude_directories"])
WATCH_ROOTS = {Path(raw) for raw in CFG["roots"]}
CONTENT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".org", ".tex", ".csv", ".tsv",
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".conf", ".log",
    ".ipynb", ".pdf", ".docx", ".pptx", ".xlsx",
    ".odt", ".odp", ".ods", ".png", ".jpg", ".jpeg", ".webp", ".tif",
    ".tiff", ".bmp",
}
MASK = (
    pyinotify.IN_CLOSE_WRITE | pyinotify.IN_MOVED_TO | pyinotify.IN_CREATE
    | pyinotify.IN_DELETE | pyinotify.IN_MOVED_FROM
)


class Handler(pyinotify.ProcessEvent):
    last_wake = 0.0

    def process_default(self, event):
        DB.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(DB, timeout=60)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("PRAGMA busy_timeout=60000")
        db.execute(
            "CREATE TABLE IF NOT EXISTS pending(path TEXT PRIMARY KEY, queued_at INTEGER NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS name_pending(path TEXT PRIMARY KEY, queued_at INTEGER NOT NULL)"
        )
        path = event.pathname
        if event.mask & (pyinotify.IN_DELETE | pyinotify.IN_MOVED_FROM):
            db.execute("DELETE FROM pending WHERE path=?", (path,))
            db.execute("DELETE FROM name_pending WHERE path=?", (path,))
            try:
                db.execute("DELETE FROM files WHERE path=?", (path,))
                db.execute("DELETE FROM files_fts WHERE path=?", (path,))
            except sqlite3.OperationalError:
                pass
        else:
            candidate = Path(path)
            if (
                (not candidate.is_file() and not candidate.is_dir())
                or set(candidate.parts).intersection(EXCLUDED_DIRECTORIES)
                or any(fnmatch.fnmatch(candidate.name.casefold(), pattern.casefold()) for pattern in CFG["exclude_globs"])
            ):
                db.close()
                return
            if candidate.is_dir() and candidate.parent in WATCH_ROOTS:
                manager.add_watch(str(candidate), MASK, rec=False, auto_add=False)
            content_worthy = candidate.is_file() and (
                candidate.suffix.casefold() in CONTENT_EXTENSIONS
                or (not candidate.suffix and candidate.stat().st_size <= 2 * 1024 * 1024)
            ) and candidate.stat().st_size <= CFG["max_file_mb"] * 1024 * 1024
            if content_worthy:
                db.execute(
                    "INSERT INTO pending(path,queued_at) VALUES(?,?) "
                    "ON CONFLICT(path) DO UPDATE SET queued_at=excluded.queued_at",
                    (path, time.time_ns()),
                )
            try:
                stat = candidate.stat()
                kind = "folder" if candidate.is_dir() else "file"
                parent = str(candidate.parent.relative_to(HOME)) if candidate.is_relative_to(HOME) else str(candidate.parent)
                mime = "inode/directory" if kind == "folder" else (mimetypes.guess_type(candidate.name)[0] or "")
                existed = db.execute("SELECT 1 FROM files WHERE path=?", (path,)).fetchone()
                if not existed:
                    db.execute(
                        "INSERT INTO files(path,name,parent,mime,size,mtime_ns,indexed_at,kind) VALUES(?,?,?,?,?,?,0,?)",
                        (path, candidate.name, parent, mime, 0 if kind == "folder" else stat.st_size, stat.st_mtime_ns, kind),
                    )
                    db.execute(
                        "INSERT INTO files_fts(path,name,parent,text) VALUES(?,?,?,?)",
                        (path, candidate.name, parent, ""),
                    )
                    db.execute(
                        "INSERT OR REPLACE INTO name_pending(path,queued_at) VALUES(?,?)",
                        (path, time.time_ns()),
                    )
            except (OSError, sqlite3.OperationalError):
                pass
        db.commit()
        db.close()
        now = time.monotonic()
        if now - self.last_wake > 20:
            subprocess.run(
                ["systemctl", "--user", "start", "--no-block", "caelestia-semantic-index.service"],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self.last_wake = now


manager = pyinotify.WatchManager()
handler = Handler()
notifier = pyinotify.Notifier(manager, handler)
for root in WATCH_ROOTS:
    if root.is_dir():
        manager.add_watch(str(root), MASK, rec=False, auto_add=False)
        try:
            for child in root.iterdir():
                if child.is_dir() and child.name not in EXCLUDED_DIRECTORIES:
                    manager.add_watch(str(child), MASK, rec=False, auto_add=False)
        except OSError:
            pass
notifier.loop()
