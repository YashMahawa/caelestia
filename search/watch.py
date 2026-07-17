#!/usr/bin/python3
"""Tiny inotify front-end: queue real changes and wake the bounded worker."""

import json
import os
import re
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
MASK = (
    pyinotify.IN_CLOSE_WRITE | pyinotify.IN_MOVED_TO | pyinotify.IN_CREATE
    | pyinotify.IN_DELETE | pyinotify.IN_MOVED_FROM
)


class Handler(pyinotify.ProcessEvent):
    last_wake = 0.0

    def process_default(self, event):
        DB.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(DB, timeout=10)
        db.execute(
            "CREATE TABLE IF NOT EXISTS pending(path TEXT PRIMARY KEY, queued_at INTEGER NOT NULL)"
        )
        path = event.pathname
        if event.mask & (pyinotify.IN_DELETE | pyinotify.IN_MOVED_FROM):
            db.execute("DELETE FROM pending WHERE path=?", (path,))
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
            ):
                db.close()
                return
            db.execute(
                "INSERT INTO pending(path,queued_at) VALUES(?,?) "
                "ON CONFLICT(path) DO UPDATE SET queued_at=excluded.queued_at",
                (path, time.time_ns()),
            )
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
exclude = pyinotify.ExcludeFilter([
    rf"(^|/){re.escape(name)}(/|$)" for name in CFG["exclude_directories"]
])
for raw in CFG["roots"]:
    root = Path(raw)
    if root.is_dir():
        manager.add_watch(
            str(root), MASK, rec=True, auto_add=True, exclude_filter=exclude
        )
notifier.loop()
