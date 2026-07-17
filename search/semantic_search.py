#!/home/yash/ML/.venv/bin/python
"""Selective, local, event-driven semantic file search for Caelestia."""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import json
import mimetypes
import os
import re
import sqlite3
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

HOME = Path.home()
APP = HOME / ".local/share/caelestia-search"
CONFIG_PATH = HOME / ".config/caelestia/semantic-search.json"
DB_PATH = APP / "index.sqlite3"
MODEL_PATH = HOME / "ML/models/embeddinggemma-300m-int4-ov"
CACHE_PATH = HOME / ".cache/caelestia-search/embeddinggemma-ov"
MODEL_ID = "embeddinggemma-300m-int4-sym-g32-ov-v1"
QUERY_EMBEDDER = None
GPU_SCORER = None

PLAIN_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".org", ".tex", ".csv", ".tsv",
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".conf", ".log",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".kt",
    ".kts", ".c", ".h", ".cc", ".cpp", ".hpp", ".rs", ".go", ".sh",
    ".bash", ".zsh", ".fish", ".sql", ".html", ".htm", ".css", ".scss",
    ".qml", ".xml", ".svg", ".ipynb", ".properties", ".desktop", ".service",
    ".timer", ".graphql", ".f", ".f90",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
OFFICE_EXTENSIONS = {".docx", ".pptx", ".xlsx", ".odt", ".odp", ".ods"}
CONTENT_TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".org", ".tex", ".csv", ".tsv",
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".conf", ".log",
    ".ipynb",
}
PROJECT_MARKERS = {
    ".git", "package.json", "pyproject.toml", "Cargo.toml", "go.mod",
    "CMakeLists.txt", "pubspec.yaml", "build.gradle", "settings.gradle",
}


def config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def connect() -> sqlite3.Connection:
    APP.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA busy_timeout=60000")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            parent TEXT NOT NULL,
            mime TEXT,
            size INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            text TEXT NOT NULL DEFAULT '',
            vector BLOB,
            vector_dim INTEGER,
            indexed_at INTEGER NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
            path UNINDEXED, name, parent, text,
            tokenize='unicode61 remove_diacritics 2'
        );
        CREATE TABLE IF NOT EXISTS pending (
            path TEXT PRIMARY KEY,
            queued_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS name_pending (
            path TEXT PRIMARY KEY,
            queued_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS visual_tags (
            path TEXT PRIMARY KEY,
            mtime_ns INTEGER NOT NULL,
            tags TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS files_mtime ON files(mtime_ns);
        """
    )
    columns = {row[1] for row in db.execute("PRAGMA table_info(files)")}
    if "kind" not in columns:
        db.execute("ALTER TABLE files ADD COLUMN kind TEXT NOT NULL DEFAULT 'file'")
    needs_name_backfill = "name_vector" not in columns
    if needs_name_backfill:
        db.execute("ALTER TABLE files ADD COLUMN name_vector BLOB")
    if "name_vector_dim" not in columns:
        db.execute("ALTER TABLE files ADD COLUMN name_vector_dim INTEGER")
    if needs_name_backfill:
        db.execute(
            "INSERT OR IGNORE INTO name_pending(path,queued_at) "
            "SELECT path,? FROM files WHERE name_vector IS NULL",
            (time.time_ns(),),
        )
    return db


def excluded(path: Path, cfg: dict) -> bool:
    try:
        relative_parts = set(path.relative_to(HOME).parts)
    except ValueError:
        relative_parts = set(path.parts)
    if relative_parts.intersection(cfg["exclude_directories"]):
        return True
    name = path.name.casefold()
    return any(fnmatch.fnmatch(name, pattern.casefold()) for pattern in cfg["exclude_globs"])


def supported(path: Path, cfg: dict) -> bool:
    try:
        stat = path.stat()
    except (FileNotFoundError, PermissionError, OSError):
        return False
    return (
        (path.is_file() or path.is_dir())
        and not path.is_symlink()
        and not excluded(path, cfg)
    )


def roots(cfg: dict) -> list[Path]:
    found = [Path(p) for p in cfg["roots"] if Path(p).is_dir()]
    if cfg.get("discover_top_level_projects", True):
        # Deliberately only an ls-like one-level probe of $HOME.
        try:
            children = list(HOME.iterdir())
        except OSError:
            children = []
        for child in children:
            try:
                is_project = any((child / marker).exists() for marker in PROJECT_MARKERS)
            except OSError:
                is_project = False
            if child.is_dir() and not child.name.startswith(".") and not excluded(child, cfg) and is_project:
                found.append(child)
    return list(dict.fromkeys(found))


def iter_files(cfg: dict):
    excluded_dirs = set(cfg["exclude_directories"])
    # Include ordinary files directly in $HOME without recursively crawling it.
    try:
        for path in HOME.iterdir():
            if path.is_file() and not path.name.startswith(".") and supported(path, cfg):
                yield path
    except OSError:
        pass
    for root in roots(cfg):
        for current, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = [
                d for d in dirs
                if d not in excluded_dirs and not excluded(Path(current) / d, cfg)
            ]
            for name in dirs:
                path = Path(current) / name
                if supported(path, cfg):
                    yield path
            for name in names:
                path = Path(current) / name
                if supported(path, cfg):
                    yield path


def content_supported(path: Path, cfg: dict) -> bool:
    """Whether content extraction is useful; every path still gets name search."""
    if not path.is_file():
        return False
    try:
        if path.stat().st_size > cfg["max_file_mb"] * 1024 * 1024:
            return False
    except OSError:
        return False
    suffix = path.suffix.casefold()
    if suffix in CONTENT_TEXT_EXTENSIONS | IMAGE_EXTENSIONS | OFFICE_EXTENSIONS | {".pdf"}:
        return True
    try:
        return not suffix and path.stat().st_size <= 2 * 1024 * 1024
    except OSError:
        return False


def command_text(command: list[str], timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=timeout, check=False,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def office_text(path: Path) -> str:
    chunks: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith(".xml"):
                    continue
                if not any(part in name for part in ("document", "slide", "sheet", "content")):
                    continue
                try:
                    root = ElementTree.fromstring(archive.read(name))
                    chunks.extend(node.text for node in root.iter() if node.text)
                except (ElementTree.ParseError, KeyError):
                    continue
    except (OSError, zipfile.BadZipFile):
        return ""
    return " ".join(chunks)


def extract_text(path: Path, cfg: dict) -> str:
    if path.is_dir():
        return ""
    suffix = path.suffix.casefold()
    limit = cfg["max_text_characters"]
    if suffix in PLAIN_EXTENSIONS or not suffix:
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:limit]
        except OSError:
            return ""
    if suffix == ".pdf":
        text = command_text(["pdftotext", "-q", "-f", "1", "-l", "80", str(path), "-"], 45)
        if len("".join(text.split())) >= 40 or not cfg["ocr"].get("pdf_fallback", True):
            return text[:limit]
        chunks: list[str] = []
        max_pages = int(cfg["ocr"].get("max_pdf_pages", 16))
        with tempfile.TemporaryDirectory(prefix="caelestia-ocr-") as temporary:
            prefix = str(Path(temporary) / "page")
            command_text(
                ["pdftoppm", "-q", "-f", "1", "-l", str(max_pages), "-jpeg", "-scale-to", "1800", str(path), prefix],
                180,
            )
            for image in sorted(Path(temporary).glob("page-*.jpg")):
                chunks.append(command_text(
                    ["tesseract", str(image), "stdout", "-l", cfg["ocr"]["languages"], "--psm", "6"], 45
                ))
                if sum(map(len, chunks)) >= limit:
                    break
        return "\n".join(chunks)[:limit]
    if suffix in OFFICE_EXTENSIONS:
        return office_text(path)[:limit]
    if suffix in IMAGE_EXTENSIONS and cfg["ocr"]["enabled"]:
        try:
            if path.stat().st_size > cfg["ocr"]["max_image_mb"] * 1024 * 1024:
                return ""
        except OSError:
            return ""
        return command_text(
            ["tesseract", str(path), "stdout", "-l", cfg["ocr"]["languages"], "--psm", "11"],
            45,
        )[:limit]
    return ""


class Embedder:
    def __init__(self, dimensions: int, *, query: bool = False, batch_size: int | None = None):
        import openvino as ov
        from tokenizers import Tokenizer

        CACHE_PATH.mkdir(parents=True, exist_ok=True)
        self.dimensions = dimensions
        self.query = query
        self.batch_size = batch_size or (1 if query else 4)
        self.sequence_length = 128
        # Long iGPU model workloads have stalled the compositor on this laptop.
        # Query-time vector scoring remains iGPU accelerated where worthwhile.
        self.device = "CPU"
        device_cache = CACHE_PATH / self.device.casefold()
        device_cache.mkdir(parents=True, exist_ok=True)
        # The low-level Rust tokenizer produces byte-for-byte identical IDs for
        # this tokenizer.json without importing Transformers and PyTorch.  That
        # avoids roughly 300 MB of unrelated runtime memory per search process.
        self.tokenizer = Tokenizer.from_file(str(MODEL_PATH / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=self.sequence_length)
        self.tokenizer.enable_padding(
            length=self.sequence_length, pad_id=0, pad_token="<pad>", direction="right"
        )
        core = ov.Core()
        model = core.read_model(MODEL_PATH / "openvino_model_pruned.xml")
        shape = [self.batch_size, self.sequence_length]
        model.reshape({
            "input_ids": shape,
            "attention_mask": shape,
            "position_ids": shape,
        })
        self.model = core.compile_model(
            model,
            self.device,
            {
                "CACHE_DIR": str(device_cache),
                "PERFORMANCE_HINT": "LATENCY" if query else "THROUGHPUT",
            },
        )
        self.output = self.model.output(0)
        dense1 = core.read_model(MODEL_PATH / "dense1.xml")
        dense1.reshape({"input": [self.batch_size, 768]})
        self.dense1 = core.compile_model(
            dense1, self.device, {"CACHE_DIR": str(device_cache)}
        )
        dense2 = core.read_model(MODEL_PATH / "dense2.xml")
        dense2.reshape({"input": [self.batch_size, 3072]})
        self.dense2 = core.compile_model(
            dense2, self.device, {"CACHE_DIR": str(device_cache)}
        )

    def encode(self, texts: list[str]) -> np.ndarray:
        count = len(texts)
        prefix = "task: search result | query: " if self.query else "title: none | text: "
        texts = [prefix + text for text in texts]
        if count < self.batch_size:
            texts.extend([texts[-1]] * (self.batch_size - count))
        encoded = self.tokenizer.encode_batch(texts)
        batch = {
            "input_ids": np.asarray([item.ids for item in encoded], dtype=np.int64),
            "attention_mask": np.asarray([item.attention_mask for item in encoded], dtype=np.int64),
        }
        batch["position_ids"] = np.broadcast_to(
            np.arange(self.sequence_length, dtype=np.int64),
            (self.batch_size, self.sequence_length),
        ).copy()
        hidden = self.model(
            {
                "input_ids": batch["input_ids"],
                "attention_mask": batch["attention_mask"],
                "position_ids": batch["position_ids"],
            }
        )[self.output]
        mask = batch["attention_mask"][..., None]
        pooled = (hidden * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1)
        projected = self.dense1(pooled)[self.dense1.output(0)]
        vectors = self.dense2(projected)[self.dense2.output(0)]
        vectors = vectors[:, : self.dimensions].astype(np.float32)
        vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9)
        return vectors[:count]


class GpuVectorScorer:
    """Reusable OpenCL cosine scorer; compilation happens once per query service."""

    def __init__(self):
        import pyopencl as cl
        self.cl = cl
        device = next(
            device for platform in cl.get_platforms()
            for device in platform.get_devices(device_type=cl.device_type.GPU)
            if "Intel" in device.vendor or "Intel" in device.name
        )
        self.context = cl.Context([device])
        self.queue = cl.CommandQueue(self.context)
        self.program = cl.Program(self.context, """
        __kernel void score(__global const float *matrix, __global const float *query,
                            __global float *scores, const int dimensions) {
            int row = get_global_id(0);
            int base = row * dimensions;
            float total = 0.0f;
            for (int column = 0; column < dimensions; ++column)
                total += matrix[base + column] * query[column];
            scores[row] = total;
        }
        """).build(options=["-cl-fast-relaxed-math"])

    def score(self, vectors: np.ndarray, query: np.ndarray) -> np.ndarray:
        cl = self.cl
        matrix = np.ascontiguousarray(vectors, dtype=np.float32)
        query = np.ascontiguousarray(query, dtype=np.float32)
        output = np.empty(len(matrix), dtype=np.float32)
        flags = cl.mem_flags
        matrix_buffer = cl.Buffer(self.context, flags.READ_ONLY | flags.COPY_HOST_PTR, hostbuf=matrix)
        query_buffer = cl.Buffer(self.context, flags.READ_ONLY | flags.COPY_HOST_PTR, hostbuf=query)
        output_buffer = cl.Buffer(self.context, flags.WRITE_ONLY, output.nbytes)
        self.program.score(
            self.queue, (len(matrix),), None, matrix_buffer, query_buffer,
            output_buffer, np.int32(matrix.shape[1]),
        )
        cl.enqueue_copy(self.queue, output, output_buffer).wait()
        return output


def queue_path(db: sqlite3.Connection, path: Path):
    db.execute(
        "INSERT INTO pending(path, queued_at) VALUES(?, ?) "
        "ON CONFLICT(path) DO UPDATE SET queued_at=excluded.queued_at",
        (str(path), time.time_ns()),
    )


def queue_name(db: sqlite3.Connection, path: Path):
    db.execute(
        "INSERT INTO name_pending(path, queued_at) VALUES(?, ?) "
        "ON CONFLICT(path) DO UPDATE SET queued_at=excluded.queued_at",
        (str(path), time.time_ns()),
    )


def discover(full: bool = False):
    cfg = config()
    db = connect()
    if full:
        db.execute("CREATE TEMP TABLE seen_paths(path TEXT PRIMARY KEY)")
    seen: set[str] = set()
    queued = 0
    for path in iter_files(cfg):
        raw = str(path)
        seen.add(raw)
        if full:
            db.execute("INSERT OR IGNORE INTO seen_paths(path) VALUES(?)", (raw,))
        stat = path.stat()
        row = db.execute("SELECT size, mtime_ns FROM files WHERE path=?", (raw,)).fetchone()
        kind = "folder" if path.is_dir() else "file"
        parent = str(path.parent.relative_to(HOME)) if path.is_relative_to(HOME) else str(path.parent)
        mime = "inode/directory" if kind == "folder" else (mimetypes.guess_type(path.name)[0] or "")
        if row is None:
            db.execute(
                "INSERT INTO files(path,name,parent,mime,size,mtime_ns,indexed_at,kind) VALUES(?,?,?,?,?,?,0,?)",
                (raw, path.name, parent, mime, 0 if kind == "folder" else stat.st_size, stat.st_mtime_ns, kind),
            )
            db.execute(
                "INSERT INTO files_fts(path,name,parent,text) VALUES(?,?,?,?)",
                (raw, path.name, parent, ""),
            )
            queue_name(db, path)
        expected_size = 0 if kind == "folder" else stat.st_size
        if full or row != (expected_size, stat.st_mtime_ns):
            if content_supported(path, cfg):
                queue_path(db, path)
                queued += 1
            else:
                db.execute("DELETE FROM pending WHERE path=?", (raw,))
    if full:
        db.execute("DELETE FROM files WHERE path NOT IN (SELECT path FROM seen_paths)")
        db.execute("DELETE FROM pending WHERE path NOT IN (SELECT path FROM seen_paths)")
        db.execute("DELETE FROM name_pending WHERE path NOT IN (SELECT path FROM seen_paths)")
        db.execute("DELETE FROM visual_tags WHERE path NOT IN (SELECT path FROM seen_paths)")
        # FTS5 has no normal index on its unindexed path column. Rebuilding once
        # is dramatically cheaper than thousands of per-path virtual-table scans.
        db.execute("DELETE FROM files_fts")
        db.execute("INSERT INTO files_fts(path,name,parent,text) SELECT path,name,parent,text FROM files")
    db.commit()
    print(json.dumps({"discovered": len(seen), "queued": queued}))


def remove_path(db: sqlite3.Connection, raw: str):
    db.execute("DELETE FROM files WHERE path=?", (raw,))
    db.execute("DELETE FROM files_fts WHERE path=?", (raw,))
    db.execute("DELETE FROM pending WHERE path=?", (raw,))
    db.execute("DELETE FROM name_pending WHERE path=?", (raw,))


def work_names(db: sqlite3.Connection, cfg: dict, limit: int = 384) -> int:
    """Give every path a semantic filename vector before costly content OCR."""
    embedder: Embedder | None = None
    processed = 0
    while processed < limit:
        batch_rows = db.execute(
            "SELECT path FROM name_pending ORDER BY queued_at DESC LIMIT 16"
        ).fetchall()
        if not batch_rows:
            break
        documents: list[tuple[str, str]] = []
        for (raw,) in batch_rows:
            path = Path(raw)
            if not supported(path, cfg):
                remove_path(db, raw)
                continue
            kind = "Folder" if path.is_dir() else "File"
            parent = str(path.parent.relative_to(HOME)) if path.is_relative_to(HOME) else str(path.parent)
            readable = path.stem.replace("_", " ").replace("-", " ")
            documents.append((raw, f"{kind}: {readable}\nFilename: {path.name}\nFolder: {parent}"))
        if not documents:
            db.commit()
            continue
        if embedder is None:
            embedder = Embedder(cfg["embedding_dimensions"], batch_size=16)
        vectors = embedder.encode([document for _raw, document in documents])
        for (raw, _document), vector in zip(documents, vectors):
            db.execute(
                "UPDATE files SET name_vector=?,name_vector_dim=? WHERE path=?",
                (vector.astype(np.float16).tobytes(), len(vector), raw),
            )
            db.execute("DELETE FROM name_pending WHERE path=?", (raw,))
            processed += 1
        db.commit()
    return processed


def work(limit: int = 0):
    cfg = config()
    db = connect()
    names_processed = work_names(db, cfg, max(128, limit * 4) if limit else 128)
    embedder: Embedder | None = None
    processed = failed = 0
    while True:
        # User documents are the main semantic-search target.  Keep source trees
        # name-searchable, but do not let a large repository rebuild hold PDFs,
        # notes, downloads, and media metadata behind thousands of code files.
        personal_prefixes = tuple(
            str(HOME / name) + os.sep
            for name in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music", "Ob", "Obsidian", "Acads")
        )
        priority_sql = " OR ".join("path LIKE ?" for _ in personal_prefixes)
        batch_rows = db.execute(
            f"""SELECT path FROM pending
                ORDER BY CASE WHEN {priority_sql} THEN 0 ELSE 1 END,
                  CASE
                    WHEN lower(path) GLOB '*.md' OR lower(path) GLOB '*.markdown'
                      OR lower(path) GLOB '*.txt' OR lower(path) GLOB '*.pdf' THEN 0
                    WHEN lower(path) GLOB '*.docx' OR lower(path) GLOB '*.odt'
                      OR lower(path) GLOB '*.png' OR lower(path) GLOB '*.jpg'
                      OR lower(path) GLOB '*.jpeg' OR lower(path) GLOB '*.webp' THEN 1
                    WHEN lower(path) GLOB '*.json' OR lower(path) GLOB '*.jsonl'
                      OR lower(path) GLOB '*.log' THEN 3
                    ELSE 2
                  END,
                  queued_at DESC LIMIT 4""",
            tuple(prefix + "%" for prefix in personal_prefixes),
        ).fetchall()
        if not batch_rows or (limit and processed >= limit):
            break
        documents: list[tuple[Path, os.stat_result, str, str]] = []
        for (raw,) in batch_rows:
            path = Path(raw)
            if not supported(path, cfg):
                remove_path(db, raw)
                continue
            try:
                stat = path.stat()
                text = extract_text(path, cfg)
                visual = db.execute("SELECT tags FROM visual_tags WHERE path=?", (raw,)).fetchone()
                if visual:
                    text = f"{text}\nVisual content: {visual[0]}".strip()
                relative = str(path.parent.relative_to(HOME)) if path.is_relative_to(HOME) else str(path.parent)
                kind = "folder" if path.is_dir() else "file"
                semantic = (
                    f"{kind.title()}: {path.name}\nParent: {relative}\n"
                    f"Type: {mimetypes.guess_type(path.name)[0] or path.suffix or kind}\n"
                    f"Content:\n{text[:cfg['embedding_characters']]}"
                )
                documents.append((path, stat, text, semantic))
            except (OSError, ValueError):
                failed += 1
                db.execute("DELETE FROM pending WHERE path=?", (raw,))
        if not documents:
            db.commit()
            continue
        if embedder is None:
            embedder = Embedder(cfg["embedding_dimensions"])
        vectors = embedder.encode([item[3] for item in documents])
        for (path, stat, text, _semantic), vector in zip(documents, vectors):
            raw = str(path)
            kind = "folder" if path.is_dir() else "file"
            mime = "inode/directory" if kind == "folder" else (mimetypes.guess_type(path.name)[0] or "")
            parent = str(path.parent.relative_to(HOME)) if path.is_relative_to(HOME) else str(path.parent)
            db.execute(
                """
                INSERT INTO files(path,name,parent,mime,size,mtime_ns,text,vector,vector_dim,indexed_at,kind)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(path) DO UPDATE SET
                  name=excluded.name,parent=excluded.parent,mime=excluded.mime,size=excluded.size,
                  mtime_ns=excluded.mtime_ns,text=excluded.text,vector=excluded.vector,
                  vector_dim=excluded.vector_dim,indexed_at=excluded.indexed_at,kind=excluded.kind
                """,
                (
                    raw, path.name, parent, mime, stat.st_size, stat.st_mtime_ns, text,
                    vector.astype(np.float16).tobytes(), len(vector), int(time.time()), kind,
                ),
            )
            db.execute("DELETE FROM files_fts WHERE path=?", (raw,))
            db.execute(
                "INSERT INTO files_fts(path,name,parent,text) VALUES(?,?,?,?)",
                (raw, path.name, parent, text),
            )
            db.execute("DELETE FROM pending WHERE path=?", (raw,))
            processed += 1
        db.commit()
    print(json.dumps({"names_processed": names_processed, "processed": processed, "failed": failed}))


def search(query: str, count: int = 20, json_output: bool = False):
    global QUERY_EMBEDDER, GPU_SCORER
    cfg = config()
    db = connect()
    rows = db.execute(
        "SELECT path,name,parent,mime,size,mtime_ns,"
        "COALESCE(vector,name_vector),COALESCE(vector_dim,name_vector_dim),kind "
        "FROM files WHERE vector IS NOT NULL OR name_vector IS NOT NULL"
    ).fetchall()
    if os.environ.get("CAELESTIA_LEXICAL_ONLY") == "1":
        rows = []
    scores = np.array([], dtype=np.float32)
    if rows:
        if QUERY_EMBEDDER is None:
            QUERY_EMBEDDER = Embedder(cfg["embedding_dimensions"], query=True)
        query_vector = QUERY_EMBEDDER.encode([query])[0]
        vectors = np.vstack([
            np.frombuffer(row[6], dtype=np.float16, count=row[7]).astype(np.float32)
            for row in rows
        ])
    else:
        vectors = np.empty((0, cfg["embedding_dimensions"]), dtype=np.float32)
    vector_scores = None
    ultra = HOME / ".local/state/caelestia/ultra-power.json"
    ultra_active = False
    try:
        ultra_active = json.loads(ultra.read_text()).get("active", False)
    except (OSError, ValueError):
        pass
    # OpenCL setup costs more than a CPU dot product for a small/incomplete
    # backfill. It becomes worthwhile once several thousand vectors exist.
    if len(rows) >= 4096 and not ultra_active:
        try:
            if GPU_SCORER is None:
                GPU_SCORER = GpuVectorScorer()
            vector_scores = GPU_SCORER.score(vectors, query_vector)
        except Exception:
            vector_scores = None
    if rows and vector_scores is None:
        vector_scores = vectors @ query_vector
    if vector_scores is not None:
        scores = vector_scores
    lexical: dict[str, float] = {}
    filename_query = "." in query and not any(character.isspace() for character in query)
    query_terms = list(dict.fromkeys(re.findall(r"[\w]+", query.casefold())))
    try:
        terms = " OR ".join(f'"{word.replace(chr(34), "")}"' for word in query_terms)
        if terms:
            document_count = max(1, int(db.execute("SELECT count(*) FROM files").fetchone()[0]))
            term_weights: dict[str, float] = {}
            for term in query_terms:
                frequency = int(db.execute(
                    "SELECT count(*) FROM files_fts WHERE files_fts MATCH ?", (f'"{term}"',)
                ).fetchone()[0])
                term_weights[term] = float(np.log((document_count + 1) / (frequency + 1)) + 1)
            total_weight = sum(term_weights.values()) or 1.0
            for position, (raw, name, parent, text, _rank) in enumerate(db.execute(
                "SELECT path,name,parent,text,bm25(files_fts,1.0,3.0,1.5,0.5) FROM files_fts "
                "WHERE files_fts MATCH ? ORDER BY rank LIMIT 100", (terms,)
            )):
                name_folded = name.casefold()
                haystack = f"{name}\n{parent}\n{text}".casefold()
                if filename_query and query.casefold() not in name_folded:
                    continue
                matched_terms = [term for term in query_terms if term in haystack]
                name_terms = [term for term in query_terms if term in name_folded]
                phrase_match = query.casefold() in haystack
                # FTS5 bm25 values are tiny negative ranks, not 0..1 scores.
                # Measure token coverage explicitly so a single incidental word
                # cannot outrank a filename or document matching the full intent.
                coverage = sum(term_weights[term] for term in matched_terms) / total_weight
                name_coverage = sum(term_weights[term] for term in name_terms) / total_weight
                if not phrase_match and coverage < 0.6 and name_coverage < 0.3:
                    continue
                rank_tiebreak = 0.05 / (1 + position / 10)
                lexical[raw] = min(
                    1.0,
                    0.55 * coverage
                    + 0.35 * name_coverage
                    + (0.45 if name_terms else 0.0)
                    + (0.15 if phrase_match else 0.0)
                    + rank_tiebreak,
                )
    except sqlite3.OperationalError:
        pass
    fuzzy: dict[str, float] = {}
    query_folded = query.casefold()
    if len(query_folded) >= 3:
        # Never run SequenceMatcher across the full index. Exact token search is
        # handled by FTS; this bounded pool exists only for genuine typos.
        needle = query_folded[:2]
        fuzzy_rows = db.execute(
            "SELECT path,name FROM files WHERE instr(lower(name),?)>0 "
            "ORDER BY abs(length(name)-?) LIMIT 2000",
            (needle, len(query_folded)),
        )
        for raw, name in fuzzy_rows:
            stem = Path(name).stem.casefold()
            tokens = [name.casefold(), stem, *stem.replace("_", " ").replace("-", " ").split()]
            similarity = max(difflib.SequenceMatcher(None, query_folded, token).ratio() for token in tokens)
            if similarity >= 0.74:
                fuzzy[raw] = similarity

    candidates: dict[str, tuple[float, tuple]] = {}
    sorted_semantic = sorted((float(value) for value in scores), reverse=True)
    semantic_confident = False
    if sorted_semantic and not filename_query:
        comparison = sorted_semantic[min(4, len(sorted_semantic) - 1)]
        semantic_confident = sorted_semantic[0] >= 0.56 and sorted_semantic[0] - comparison >= 0.04
    for index, row in enumerate(rows):
        name_bonus = 0.8 if query_folded in row[1].casefold() else 0.0
        lexical_score = lexical.get(row[0], 0.0)
        fuzzy_score = fuzzy.get(row[0], 0.0)
        semantic_score = float(scores[index])
        # Weak semantic similarities are worse than an honest empty result.
        if not lexical_score and not fuzzy_score and not name_bonus and (not semantic_confident or semantic_score < 0.58):
            continue
        suffix = Path(row[1]).suffix.casefold()
        content_quality = 1.12 if suffix in {".md", ".markdown", ".rst", ".org", ".txt", ".pdf"} else (0.82 if suffix in {".json", ".jsonl", ".log"} else 1.0)
        combined = semantic_score + 0.9 * lexical_score * content_quality + 0.65 * fuzzy_score + name_bonus
        candidates[row[0]] = (combined, row)
    named_paths = set(lexical) | set(fuzzy)
    if named_paths:
        placeholders = ",".join("?" for _ in named_paths)
        for row in db.execute(
            f"SELECT path,name,parent,mime,size,mtime_ns,vector,vector_dim,kind FROM files WHERE path IN ({placeholders})",
            tuple(named_paths),
        ):
            if row[0] in candidates:
                continue
            name_bonus = 0.8 if query_folded in row[1].casefold() else 0.0
            suffix = Path(row[1]).suffix.casefold()
            content_quality = 1.12 if suffix in {".md", ".markdown", ".rst", ".org", ".txt", ".pdf"} else (0.82 if suffix in {".json", ".jsonl", ".log"} else 1.0)
            combined = 0.9 * lexical.get(row[0], 0.0) * content_quality + 0.65 * fuzzy.get(row[0], 0.0) + name_bonus
            candidates[row[0]] = (combined, row)
    ranked = sorted(candidates.values(), key=lambda item: item[0], reverse=True)[:count]
    results = [{
        "path": row[0], "name": row[1], "parent": row[2], "mime": row[3],
        "size": row[4], "mtime_ns": row[5], "kind": row[8], "score": round(score, 5),
    } for score, row in ranked]
    if json_output:
        print(json.dumps(results, ensure_ascii=False))
    else:
        for result in results:
            print(f"{result['score']:.4f}\t{result['path']}")


def serve():
    global QUERY_EMBEDDER
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    socket_path = runtime / "caelestia-semantic-search.sock"
    socket_path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    server.listen(4)
    server.settimeout(45)
    # Launcher startup pre-warms the compact query model while apps are already
    # visible, so semantic results are fast by the time the user finishes typing.
    QUERY_EMBEDDER = Embedder(config()["embedding_dimensions"], query=True)
    try:
        while True:
            try:
                connection, _ = server.accept()
            except TimeoutError:
                break
            with connection:
                request = b""
                while not request.endswith(b"\n") and len(request) < 65536:
                    part = connection.recv(65536)
                    if not part:
                        break
                    request += part
                try:
                    payload = json.loads(request)
                    import io
                    from contextlib import redirect_stdout
                    output = io.StringIO()
                    with redirect_stdout(output):
                        search(str(payload["query"]), min(int(payload.get("count", 10)), 20), True)
                    response = output.getvalue().strip() or "[]"
                except Exception as error:
                    response = json.dumps({"error": str(error)[:200]})
                try:
                    connection.sendall(response.encode("utf-8") + b"\n")
                except (BrokenPipeError, ConnectionResetError):
                    # Superseded launcher queries disconnect by design.
                    pass
    finally:
        server.close()
        socket_path.unlink(missing_ok=True)


def status():
    db = connect()
    files = db.execute("SELECT count(*) FROM files").fetchone()[0]
    pending = db.execute("SELECT count(*) FROM pending").fetchone()[0]
    name_pending = db.execute("SELECT count(*) FROM name_pending").fetchone()[0]
    name_vectors = db.execute("SELECT count(*) FROM files WHERE name_vector IS NOT NULL").fetchone()[0]
    size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    print(json.dumps({"files": files, "pending": pending, "name_pending": name_pending,
                      "name_vectors": name_vectors, "database_bytes": size}))


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan")
    scan.add_argument("--full", action="store_true")
    worker = commands.add_parser("work")
    worker.add_argument("--limit", type=int, default=0)
    finder = commands.add_parser("search")
    finder.add_argument("query")
    finder.add_argument("-n", "--count", type=int, default=20)
    finder.add_argument("--json", action="store_true")
    commands.add_parser("status")
    commands.add_parser("serve")
    args = parser.parse_args()
    if args.command == "scan":
        discover(args.full)
    elif args.command == "work":
        work(args.limit)
    elif args.command == "search":
        search(args.query, args.count, args.json)
    elif args.command == "status":
        status()
    elif args.command == "serve":
        serve()


if __name__ == "__main__":
    main()
