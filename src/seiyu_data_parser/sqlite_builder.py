import argparse
import base64
import hashlib
import json
import os
import sqlite3
from typing import Any, Dict, Iterable, List, Optional


def parse_args():
    parser = argparse.ArgumentParser(description="Build a SQLite database from voice actor JSON")
    parser.add_argument("path", help="Path to voice_actor.json")
    parser.add_argument(
        "--output",
        "-o",
        default="voice_actor.sqlite3",
        help="Output SQLite file path (default: ./voice_actor.sqlite3)",
    )
    return parser.parse_args()


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _hash_wiki_title(wiki_title: str) -> Optional[str]:
    wiki_title = _normalize_text(wiki_title)
    if not wiki_title:
        return None
    digest = hashlib.blake2b(wiki_title.encode("utf-8"), digest_size=12).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _normalize_year(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _load_actors(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, dict):
        actors = payload.get("actors", [])
    else:
        actors = payload
    return actors if isinstance(actors, list) else []


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS voice_actors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            wiki_title TEXT,
            wiki_title_hash TEXT
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_voice_actors_wiki_title_hash
            ON voice_actors(wiki_title_hash);

        CREATE TABLE IF NOT EXISTS works (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media TEXT NOT NULL,
            title TEXT NOT NULL,
            UNIQUE(media, title)
        );

        CREATE TABLE IF NOT EXISTS voice_actor_work_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voice_actor_id INTEGER NOT NULL,
            work_id INTEGER NOT NULL,
            year INTEGER,
            FOREIGN KEY (voice_actor_id) REFERENCES voice_actors(id) ON DELETE CASCADE,
            FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_voice_actor_work_mappings_unique
            ON voice_actor_work_mappings(
                voice_actor_id,
                work_id,
                COALESCE(year, -1)
            );
        """
    )


def _get_id(conn: sqlite3.Connection, query: str, params: Iterable[Any]) -> int:
    row = conn.execute(query, tuple(params)).fetchone()
    if row is None:
        raise RuntimeError("failed to fetch inserted row id")
    return int(row[0])


def _upsert_voice_actor(conn: sqlite3.Connection, actor: Dict[str, Any]) -> int:
    name = _normalize_text(actor.get("name"))
    if not name:
        raise ValueError("voice actor name is required")
    wiki_title = _normalize_text(actor.get("wiki_title")) or None
    wiki_title_hash = _hash_wiki_title(wiki_title) if wiki_title else None
    conn.execute(
        "INSERT OR IGNORE INTO voice_actors(name, wiki_title, wiki_title_hash) VALUES (?, ?, ?)",
        (name, wiki_title, wiki_title_hash),
    )
    if wiki_title:
        conn.execute(
            """
            UPDATE voice_actors
               SET wiki_title = COALESCE(NULLIF(wiki_title, ''), ?),
                   wiki_title_hash = COALESCE(NULLIF(wiki_title_hash, ''), ?)
             WHERE name = ?
            """,
            (wiki_title, wiki_title_hash, name),
        )
    return _get_id(conn, "SELECT id FROM voice_actors WHERE name = ?", (name,))


def _upsert_work(conn: sqlite3.Connection, media: str, title: str) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO works(media, title) VALUES (?, ?)",
        (media, title),
    )
    return _get_id(conn, "SELECT id FROM works WHERE media = ? AND title = ?", (media, title))


def _iter_credits(works: Any) -> Iterable[Dict[str, Any]]:
    if not isinstance(works, list):
        return []
    for media_block in works:
        if not isinstance(media_block, dict):
            continue
        media = _normalize_text(media_block.get("media"))
        credits = media_block.get("credits", [])
        if not media or not isinstance(credits, list):
            continue
        for credit in credits:
            if isinstance(credit, dict):
                item = dict(credit)
                item["media"] = media
                yield item


def build_sqlite(input_json: str, output_db: str) -> None:
    actors = _load_actors(input_json)
    os.makedirs(os.path.dirname(output_db) or ".", exist_ok=True)

    with sqlite3.connect(output_db) as conn:
        _ensure_schema(conn)
        for actor in actors:
            if not isinstance(actor, dict):
                continue
            actor_id = _upsert_voice_actor(conn, actor)
            works = actor.get("works", [])
            for credit in _iter_credits(works):
                media = _normalize_text(credit.get("media"))
                title = _normalize_text(credit.get("title"))
                if not media or not title:
                    continue
                work_id = _upsert_work(conn, media, title)
                year = _normalize_year(credit.get("year"))
                conn.execute(
                    """
                    INSERT OR IGNORE INTO voice_actor_work_mappings(voice_actor_id, work_id, year)
                    VALUES (?, ?, ?)
                    """,
                    (actor_id, work_id, year),
                )
        conn.commit()


def main() -> None:
    args = parse_args()
    if not os.path.exists(args.path):
        raise SystemExit(f"Input file not found: {args.path}")
    build_sqlite(args.path, args.output)


if __name__ == "__main__":
    main()
