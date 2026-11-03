import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .models import Showtime


def normalized(value: str) -> str:
    return " ".join(value.casefold().split())


class Database:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS imports (
                    id INTEGER PRIMARY KEY, source TEXT NOT NULL,
                    created_at TEXT NOT NULL, images TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS showtimes (
                    id INTEGER PRIMARY KEY, import_id INTEGER NOT NULL REFERENCES imports(id),
                    movie TEXT NOT NULL, cinema TEXT NOT NULL, theater_type TEXT NOT NULL,
                    starts_at TEXT NOT NULL, metadata TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS deliveries (
                    delivery_key TEXT PRIMARY KEY, sent_at TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            yield db

    def save(self, source: str, images: list[str], showtimes: list[Showtime]) -> int:
        # Store an entire snapshot atomically; unsuccessful extraction never replaces it.
        with self.connect() as db:
            cursor = db.execute("INSERT INTO imports(source,created_at,images) VALUES(?,?,?)",
                                (source, datetime.now(timezone.utc).isoformat(), json.dumps(images)))
            import_id = cursor.lastrowid
            seen = set()
            for show in showtimes:
                start = show.starts_at.astimezone(timezone.utc).isoformat()
                key = (normalized(show.movie), normalized(show.cinema), normalized(show.theater_type), start)
                if key in seen:
                    continue
                seen.add(key)
                db.execute('''INSERT INTO showtimes(import_id,movie,cinema,theater_type,starts_at,metadata)
                              VALUES(?,?,?,?,?,?)''',
                           (import_id, show.movie, show.cinema, show.theater_type, start,
                            json.dumps(show.metadata.model_dump())))
            return import_id

    def latest(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('''SELECT s.*, i.source FROM showtimes s JOIN imports i ON i.id=s.import_id
                WHERE i.id IN (SELECT MAX(id) FROM imports GROUP BY source)
                ORDER BY s.starts_at''').fetchall()
            return [dict(row) | {"metadata": json.loads(row["metadata"])} for row in rows]

    def matches(self, request, now=None) -> list[dict]:
        now = now or datetime.now(timezone.utc)
        return [show for show in self.latest()
                if normalized(show["movie"]) == normalized(request.movie)
                and normalized(show["theater_type"]) == normalized(request.theater_type)
                and (not request.cinema or normalized(show["cinema"]) == normalized(request.cinema))
                and datetime.fromisoformat(show["starts_at"]) > now]
