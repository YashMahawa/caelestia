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
TRASH_INFO = HOME / ".local/share/Trash/info"
CFG = json.loads(CONFIG.read_text())
EXCLUDED_DIRECTORIES = set(CFG["exclude_directories"])
WATCH_ROOTS = {Path(raw).expanduser() for raw in CFG["roots"]}
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


def excluded_watch_path(raw_path):
    """Keep recursive watches out of caches, repositories and secret trees."""
    candidate = Path(raw_path)
    return (
        bool(set(candidate.parts).intersection(EXCLUDED_DIRECTORIES))
        or any(
            fnmatch.fnmatch(candidate.name.casefold(), pattern.casefold())
            for pattern in CFG["exclude_globs"]
        )
    )


def candidate_tree(candidate):
    """Yield a new directory and anything that arrived with it."""
    yield candidate
    if not candidate.is_dir():
        return
    for directory, child_dirs, files in os.walk(candidate):
        directory = Path(directory)
        child_dirs[:] = [
            name for name in child_dirs
            if not excluded_watch_path(directory / name)
        ]
        if directory != candidate:
            yield directory
        for name in files:
            child = directory / name
            if not excluded_watch_path(child):
                yield child


def record_candidate(db, candidate):
    if not (candidate.is_file() or candidate.is_dir()):
        return
    stat = candidate.stat()
    path = str(candidate)
    content_worthy = candidate.is_file() and (
        candidate.suffix.casefold() in CONTENT_EXTENSIONS
        or (not candidate.suffix and stat.st_size <= 2 * 1024 * 1024)
    ) and stat.st_size <= CFG["max_file_mb"] * 1024 * 1024
    if content_worthy:
        db.execute(
            "INSERT INTO pending(path,queued_at) VALUES(?,?) "
            "ON CONFLICT(path) DO UPDATE SET queued_at=excluded.queued_at",
            (path, time.time_ns()),
        )
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
        trash_event = Path(path).is_relative_to(TRASH_INFO)
        if event.mask & (pyinotify.IN_DELETE | pyinotify.IN_MOVED_FROM):
            escaped_path = path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            descendants = escaped_path + os.sep + "%"
            db.execute(
                "DELETE FROM pending WHERE path=? OR path LIKE ? ESCAPE '\\'",
                (path, descendants),
            )
            db.execute(
                "DELETE FROM name_pending WHERE path=? OR path LIKE ? ESCAPE '\\'",
                (path, descendants),
            )
            # Do not destroy vectors here: a move to freedesktop Trash should
            # hide the item but retain its index for an instant restore. The
            # delayed full scan distinguishes Trash moves from true deletion.
        else:
            candidate = Path(path)
            if (
                (not candidate.is_file() and not candidate.is_dir())
                or (excluded_watch_path(candidate) and not trash_event)
            ):
                db.close()
                return
            if candidate.is_dir() and not trash_event:
                manager.add_watch(
                    str(candidate), MASK, rec=True, auto_add=True,
                    exclude_filter=excluded_watch_path,
                )
            if not trash_event:
                try:
                    for discovered in candidate_tree(candidate):
                        record_candidate(db, discovered)
                except (OSError, sqlite3.OperationalError):
                    pass
        db.commit()
        db.close()
        now = time.monotonic()
        if event.mask & (pyinotify.IN_DELETE | pyinotify.IN_MOVED_FROM) or trash_event:
            subprocess.run(
                ["systemd-run", "--user", "--collect", "--unit=caelestia-search-reconcile",
                 "--on-active=1s", str(HOME / ".local/bin/caelestia-search"), "scan"],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        if not trash_event and now - self.last_wake > 20:
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
        manager.add_watch(
            str(root), MASK, rec=True, auto_add=True,
            exclude_filter=excluded_watch_path,
        )
if TRASH_INFO.is_dir():
    manager.add_watch(str(TRASH_INFO), MASK, rec=False, auto_add=False)
notifier.loop()
