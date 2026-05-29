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


def _compute_bigrams(name: str) -> Optional[str]:
    """Compute bigrams (N=2) from a name without normalization.

    Rules:
    - Do not perform case normalization or Unicode normalization.
    - Remove spaces before generating bigrams (so multi-word names are treated
      as a contiguous sequence of characters).
    - If the resulting string has length < 2, return None.
    - Return a space-separated string of bigrams (e.g. "ab bc cd").
    """
    if not isinstance(name, str):
        return None
    s = name.replace(" ", "")
    if len(s) < 2:
        return None
    # Generate overlapping bigrams
    grams = [s[i : i + 2] for i in range(len(s) - 1)]
    return " ".join(grams)


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

def _normalize_date(value: Any) -> Optional[str]:
    """
    Normalize various date representations into ISO YYYY-MM-DD strings.
    Accepts:
      - ISO strings "YYYY-MM-DD"
      - Common separators "YYYY/MM/DD", "YYYY.MM.DD"
      - Year-only (int or "YYYY") -> returns "YYYY-01-01"
    Returns None when input is empty or cannot be parsed.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return f"{value:04d}-01-01"
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        import re
        from datetime import datetime

        # Already ISO
        if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            return v
        # Common alternate formats
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
            try:
                return datetime.strptime(v, fmt).date().isoformat()
            except ValueError:
                pass
        # Year-month or year-only fallbacks
        if re.match(r"^\d{4}-\d{2}$", v):
            return v + "-01"
        if re.match(r"^\d{4}$", v):
            return v + "-01-01"
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
            -- name_ngrams stores space-separated bigrams (N=2) for the name
            -- e.g. "あい いう うえ"
            name_ngrams TEXT,
            canonical_name TEXT,
            canonical_name_hash TEXT,
            -- Optional phonetic reading and its ngrams
            furigana TEXT,
            furigana_ngrams TEXT,
            -- Agency and its ngrams
            agency TEXT,
            agency_ngrams TEXT,
            -- Official website URL
            official_site TEXT,
            -- Birth date stored in ISO YYYY-MM-DD (SQLite DATE affinity)
            birth_date DATE,
            -- Death date stored in ISO YYYY-MM-DD (SQLite DATE affinity)
            death_date DATE,
            -- Gender inferred from categories (e.g. male/female)
            gender TEXT
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
            canonical_name TEXT NOT NULL,
            canonical_name_hash TEXT,
            -- canonical_name is the primary identifier for works in the new schema
            UNIQUE(canonical_name),
            UNIQUE(canonical_name_hash)
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

        -- FTS5 table to index bigrams for fast partial-match search. Use an
        -- external-content FTS5 table that references voice_actors so that
        -- the FTS module can obtain column values and the special FTS5
        -- commands can be used for delete/update operations. Bind the FTS
        -- rowid to voice_actors.id.
        CREATE VIRTUAL TABLE IF NOT EXISTS voice_actors_ngrams_fts USING fts5(
            name_ngrams, furigana_ngrams, agency_ngrams, content='voice_actors', content_rowid='id'
        );

        -- Triggers to keep the FTS table in sync with voice_actors.
        CREATE TRIGGER IF NOT EXISTS trg_voice_actors_fts_after_insert
        AFTER INSERT ON voice_actors
        FOR EACH ROW
        WHEN NEW.name_ngrams IS NOT NULL OR NEW.furigana_ngrams IS NOT NULL OR NEW.agency_ngrams IS NOT NULL
        BEGIN
            INSERT INTO voice_actors_ngrams_fts(rowid, name_ngrams, furigana_ngrams, agency_ngrams)
            VALUES (NEW.id, NEW.name_ngrams, NEW.furigana_ngrams, NEW.agency_ngrams);
        END;

        CREATE TRIGGER IF NOT EXISTS trg_voice_actors_fts_after_update
        AFTER UPDATE ON voice_actors
        FOR EACH ROW
        BEGIN
            -- Remove old tokens from the FTS index using the special 'delete'
            -- command, then insert the new tokens when present.
            INSERT INTO voice_actors_ngrams_fts(voice_actors_ngrams_fts, rowid, name_ngrams, furigana_ngrams, agency_ngrams)
            VALUES('delete', OLD.id, OLD.name_ngrams, OLD.furigana_ngrams, OLD.agency_ngrams);
            INSERT INTO voice_actors_ngrams_fts(rowid, name_ngrams, furigana_ngrams, agency_ngrams)
            SELECT NEW.id, NEW.name_ngrams, NEW.furigana_ngrams, NEW.agency_ngrams
            WHERE NEW.name_ngrams IS NOT NULL OR NEW.furigana_ngrams IS NOT NULL OR NEW.agency_ngrams IS NOT NULL;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_voice_actors_ngrams_fts_after_delete
        AFTER DELETE ON voice_actors
        FOR EACH ROW
        BEGIN
            -- Use FTS5 delete command to remove index entries for the deleted row.
            INSERT INTO voice_actors_ngrams_fts(voice_actors_ngrams_fts, rowid, name_ngrams, furigana_ngrams, agency_ngrams)
            VALUES('delete', OLD.id, OLD.name_ngrams, OLD.furigana_ngrams, OLD.agency_ngrams);
        END;
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

    # Compute bigrams for the name (no normalization beyond space removal)
    name_ngrams = _compute_bigrams(name)

    # New optional fields
    furigana = _normalize_text(actor.get("furigana"))
    furigana_ngrams = _compute_bigrams(furigana) if furigana else None
    agency = _normalize_text(actor.get("agency"))
    agency_ngrams = _compute_bigrams(agency) if agency else None
    official_site = _normalize_text(actor.get("official_site"))
    birth_date = _normalize_date(actor.get("birth_date"))
    death_date = _normalize_date(actor.get("death_date"))
    gender = _normalize_text(actor.get("gender"))

    if canonical_name:
        # Prefer inserting/looking up by canonical_name (it's unique when present).
        conn.execute(
            "INSERT OR IGNORE INTO voice_actors(canonical_name, canonical_name_hash, name, name_ngrams, furigana, furigana_ngrams, agency, agency_ngrams, official_site, birth_date, death_date, gender) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                canonical_name,
                canonical_name_hash,
                name,
                name_ngrams,
                furigana,
                furigana_ngrams,
                agency,
                agency_ngrams,
                official_site,
                birth_date,
                death_date,
                gender,
            ),
        )
        # Ensure the record has fields populated when they were previously empty.
        conn.execute(
            """
            UPDATE voice_actors
               SET name = COALESCE(NULLIF(name, ''), ?),
                   name_ngrams = COALESCE(NULLIF(name_ngrams, ''), ?),
                   furigana = COALESCE(NULLIF(furigana, ''), ?),
                   furigana_ngrams = COALESCE(NULLIF(furigana_ngrams, ''), ?),
                   agency = COALESCE(NULLIF(agency, ''), ?),
                   agency_ngrams = COALESCE(NULLIF(agency_ngrams, ''), ?),
                   official_site = COALESCE(NULLIF(official_site, ''), ?),
                   birth_date = COALESCE(NULLIF(birth_date, ''), ?),
                   death_date = COALESCE(NULLIF(death_date, ''), ?),
                   gender = COALESCE(NULLIF(gender, ''), ?)
             WHERE canonical_name = ?
            """,
            (
                name,
                name_ngrams,
                furigana,
                furigana_ngrams,
                agency,
                agency_ngrams,
                official_site,
                birth_date,
                death_date,
                gender,
                canonical_name,
            ),
        )
        return _get_id(conn, "SELECT id FROM voice_actors WHERE canonical_name = ?", (canonical_name,))
    else:
        # Legacy path: no canonical_name provided. Insert by name (non-unique
        # names are allowed) and return the first matching id.
        conn.execute(
            "INSERT OR IGNORE INTO voice_actors(name, name_ngrams, furigana, furigana_ngrams, agency, agency_ngrams, official_site, birth_date, death_date, gender) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, name_ngrams, furigana, furigana_ngrams, agency, agency_ngrams, official_site, birth_date, death_date, gender),
        )
        # Return one id that matches the name (order by id to be deterministic).
        return _get_id(conn, "SELECT id FROM voice_actors WHERE name = ? ORDER BY id LIMIT 1", (name,))


def _upsert_work(conn: sqlite3.Connection, media: str, title: str, wiki_title: str) -> int:
    # New behavior: works are identified by canonical_name. The old wiki_title
    # parameter is no longer used as the primary identifier. To preserve a
    # small amount of context we accept the old "wiki_title" param as a
    # fallback when canonical_name is not provided by callers, but callers in
    # this codebase should pass canonical_name explicitly.
    #
    # For compatibility with the existing call sites in this file we allow the
    # original signature but treat the passed-in wiki_title value as the
    # canonical_name when callers didn't update yet.
    title = _normalize_text(title)
    canonical_name = _normalize_text(wiki_title) or title
    if not title or not canonical_name:
        raise ValueError("work title and canonical_name are required")

    canonical_name_hash = _hash_canonical_name(canonical_name)

    # Insert-or-ignore by canonical_name
    conn.execute(
        "INSERT OR IGNORE INTO works(canonical_name, canonical_name_hash, media, title) VALUES (?, ?, ?, ?)",
        (canonical_name, canonical_name_hash, media, title),
    )
    # Ensure fields get populated/updated if the record already existed
    conn.execute(
        """
        UPDATE works
           SET media = COALESCE(NULLIF(media, ''), ?),
               title = COALESCE(NULLIF(title, ''), ?)
         WHERE canonical_name = ?
        """,
        (media, title, canonical_name),
    )
    return _get_id(conn, "SELECT id FROM works WHERE canonical_name = ?", (canonical_name,))


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
                # Use canonical_name as the primary work identifier. Fall back
                # to wiki_title or title only if canonical_name is missing.
                canonical_name = (
                    _normalize_text(credit.get("canonical_name"))
                    or _normalize_text(credit.get("wiki_title"))
                    or title
                )
                if not media or not title or not canonical_name:
                    continue
                work_id = _upsert_work(conn, media, title, canonical_name)
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
