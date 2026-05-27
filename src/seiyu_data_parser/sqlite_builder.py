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


def _hash_canonical_name(canonical_name: str) -> Optional[str]:
    """Generate a short, URL-safe hash for a canonical name.

    This replaces the previous wiki_title hashing. Accepts the canonical
    (normalized) name and returns a base64 urlsafe string without padding,
    or None if the input is empty.
    """
    canonical_name = _normalize_text(canonical_name)
    if not canonical_name:
        return None
    digest = hashlib.blake2b(canonical_name.encode("utf-8"), digest_size=12).digest()
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
            name TEXT NOT NULL,
            canonical_name TEXT,
            canonical_name_hash TEXT
        );

        -- Unique indexes on canonical_name and its short hash. NULL values are
        -- allowed during backfill; SQLite permits multiple NULLs for unique
        -- indexes which makes migrations safer.
        CREATE UNIQUE INDEX IF NOT EXISTS idx_voice_actors_canonical_name
            ON voice_actors(canonical_name);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_voice_actors_canonical_name_hash
            ON voice_actors(canonical_name_hash);

        CREATE TABLE IF NOT EXISTS works (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media TEXT NOT NULL,
            title TEXT NOT NULL,
            wiki_title TEXT NOT NULL UNIQUE
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

        -- New table to store role names for a given voice_actor_work_mappings entry.
        -- A mapping (voice actor + work + optional year) can have multiple role names.
        CREATE TABLE IF NOT EXISTS voice_actor_work_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mapping_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            FOREIGN KEY (mapping_id) REFERENCES voice_actor_work_mappings(id) ON DELETE CASCADE
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_voice_actor_work_roles_unique
            ON voice_actor_work_roles(mapping_id, role);
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

    # Backwards-compatible: accept either `canonical_name` (new) or
    # `wiki_title` (legacy) from incoming actor payloads.
    canonical_name = _normalize_text(actor.get("canonical_name") or actor.get("wiki_title")) or None
    canonical_name_hash = _hash_canonical_name(canonical_name) if canonical_name else None

    if canonical_name:
        # Prefer inserting/looking up by canonical_name (it's unique when present).
        conn.execute(
            "INSERT OR IGNORE INTO voice_actors(canonical_name, canonical_name_hash, name) VALUES (?, ?, ?)",
            (canonical_name, canonical_name_hash, name),
        )
        # Ensure the record has a name if it was previously empty.
        conn.execute(
            """
            UPDATE voice_actors
               SET name = COALESCE(NULLIF(name, ''), ?)
             WHERE canonical_name = ?
            """,
            (name, canonical_name),
        )
        return _get_id(conn, "SELECT id FROM voice_actors WHERE canonical_name = ?", (canonical_name,))
    else:
        # Legacy path: no canonical_name provided. Insert by name (non-unique
        # names are allowed) and return the first matching id.
        conn.execute(
            "INSERT OR IGNORE INTO voice_actors(name) VALUES (?)",
            (name,),
        )
        # Return one id that matches the name (order by id to be deterministic).
        return _get_id(conn, "SELECT id FROM voice_actors WHERE name = ? ORDER BY id LIMIT 1", (name,))


def _upsert_work(conn: sqlite3.Connection, media: str, title: str, wiki_title: str) -> int:
    title = _normalize_text(title)
    wiki_title = _normalize_text(wiki_title) or title
    if not title or not wiki_title:
        raise ValueError("work title is required")
    conn.execute(
        "INSERT OR IGNORE INTO works(media, title, wiki_title) VALUES (?, ?, ?)",
        (media, title, wiki_title),
    )
    if title:
        conn.execute(
            """
            UPDATE works
               SET title = COALESCE(NULLIF(title, ''), ?),
                   media = COALESCE(NULLIF(media, ''), ?)
             WHERE wiki_title = ?
            """,
            (title, media, wiki_title),
        )
    return _get_id(conn, "SELECT id FROM works WHERE wiki_title = ?", (wiki_title,))


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
                wiki_title = _normalize_text(credit.get("wiki_title")) or title
                if not media or not title or not wiki_title:
                    continue
                work_id = _upsert_work(conn, media, title, wiki_title)
                year = _normalize_year(credit.get("year"))
                conn.execute(
                    """
                    INSERT OR IGNORE INTO voice_actor_work_mappings(voice_actor_id, work_id, year)
                    VALUES (?, ?, ?)
                    """,
                    (actor_id, work_id, year),
                )
                # Fetch the mapping id (either newly inserted or existing) so roles can reference it
                mapping_id = _get_id(
                    conn,
                    "SELECT id FROM voice_actor_work_mappings WHERE voice_actor_id = ? AND work_id = ? AND COALESCE(year, -1) = COALESCE(?, -1)",
                    (actor_id, work_id, year),
                )
                # Insert role names (if any) associated with this mapping
                roles = credit.get("roles", [])
                if isinstance(roles, list):
                    for role in roles:
                        role_text = _normalize_text(role)
                        if role_text:
                            conn.execute(
                                "INSERT OR IGNORE INTO voice_actor_work_roles(mapping_id, role) VALUES (?, ?)",
                                (mapping_id, role_text),
                            )
        conn.commit()


def main() -> None:
    args = parse_args()
    if not os.path.exists(args.path):
        raise SystemExit(f"Input file not found: {args.path}")
    build_sqlite(args.path, args.output)


if __name__ == "__main__":
    main()
