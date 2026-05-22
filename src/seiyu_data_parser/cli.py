import argparse
import json
import os
import sys
import re
from typing import Any, Dict, List
from .io import open_bz2
from .wikistream import iter_pages
from . import extract

def _normalize_media(s: str) -> str:
    if not isinstance(s, str):
        return ""
    # Normalize common punctuation and full-width spaces; keep case as-is for Japanese.
    return s.replace('、', ',').replace('　', ' ').strip()


def _strip_parenthetical(title: str) -> str:
    """Remove half-width and full-width parentheses and their contents from a wiki title.

    Examples:
    - "くじら (声優)" -> "くじら"
    - "名前（補足）" -> "名前"
    """
    if not isinstance(title, str):
        return ""
    # remove half-width parentheses and contents
    title = re.sub(r'\s*\(.*?\)', '', title)
    # remove full-width parentheses and contents
    title = re.sub(r'\s*（.*?）', '', title)
    return title.strip()

def parse_args():
    parser = argparse.ArgumentParser(description="seiyu data parser")
    parser.add_argument("path", help="Path to .bz2 file (Wikipedia multistream dump)")
    parser.add_argument("--limit", type=int, default=100, help="Max number of pages to scan and max number of matching pages to output")
    parser.add_argument("--output", "-o", default="voice_actor.json", help="Output JSON file path (default: ./voice_actor.json)")
    parser.add_argument(
        "--exclude-media",
        "-e",
        action="append",
        default=[
            "バラエティ",
            "ラジオ",
            "舞台",
            "その他コンテンツ",
            "CD",
            "その他",
            "担当俳優",
            "CM",
            "レコード、CD",
            "過去",
            "現在",
            "レギュラー",
            "不定期",
            "テレビ番組",
            "特別番組",
            "俳優",
            "女優",
            "担当女優",
            "担当",
            "映画（吹き替え）",
            "吹き替え",
            "テレビドラマ",
            "ドラマ",
        ],
        help="Media names to exclude from output (can be specified multiple times). Defaults include common non-target media."
    )
    return parser.parse_args()

def main():
    args = parse_args()
    # verify input file exists before attempting to open
    if not os.path.exists(args.path):
        print(f"Input file not found: {args.path}", file=sys.stderr)
        sys.exit(2)
    output_count = 0
    scanned = 0
    max_scan = args.limit
    max_output = args.limit

    # batching / streaming output settings
    BATCH_SIZE = 30  # write every BATCH_SIZE actors
    tmp = args.output + ".tmp"
    os.makedirs("data", exist_ok=True)

    try:
        with open_bz2(args.path) as fh, open(tmp, "w", encoding="utf-8") as outfh:
            # begin top-level wrapper object with "actors" array
            outfh.write('{"actors":[\n')
            first = True
            buffer: List[Dict[str, Any]] = []

            for page_xml in iter_pages(fh):
                scanned += 1
                title, cats = extract.extract_title_and_categories(page_xml)
                if cats:
                    section = extract.extract_section(page_xml, "出演")
                    if section:
                        with open("data/debug_detail.txt", "a", encoding="utf-8") as ddf:
                            ddf.write(section + "\n\n")
                    works = extract.parse_works_section(section)
                    result_item: Dict[str, Any] = {"name": _strip_parenthetical(title), "wiki_title": title}
                    if works:
                        result_item["works"] = works

                    # append to buffer and flush if needed
                    buffer.append(result_item)
                    output_count += 1

                    if len(buffer) >= BATCH_SIZE:
                        # prepare grouped entries and write batch
                        for actor in buffer:
                            # apply grouping/exclusion (same logic as before)
                            exclude_set = set(_normalize_media(m) for m in (args.exclude_media or []) if isinstance(m, str))
                            works = actor.get("works")
                            if works:
                                grouped = {}
                                filtered = [
                                    w for w in works
                                    if not (isinstance(w.get("media"), str) and _normalize_media(w.get("media")) in exclude_set)
                                ]
                                for w in filtered:
                                    media = w.get("media", "Unknown")
                                    entry = {k: v for k, v in w.items() if k != "media"}
                                    grouped.setdefault(media, []).append(entry)
                                actor["works"] = [{"media": m, "credits": c} for m, c in grouped.items()]
                            # write actor JSON into stream, manage commas, pretty-print
                            actor_json = json.dumps(actor, ensure_ascii=False, indent=2)
                            indented = '\n'.join('  ' + l for l in actor_json.splitlines())
                            if not first:
                                outfh.write(",\n")
                            outfh.write(indented)
                            # show progress: output completed actor name to stdout
                            print(actor.get("name", ""), flush=True)
                            first = False
                        outfh.flush()
                        buffer.clear()

                    if output_count >= max_output:
                        break
                if scanned >= max_scan:
                    break

            # write any remaining buffered actors
            if buffer:
                exclude_set = set(_normalize_media(m) for m in (args.exclude_media or []) if isinstance(m, str))
                for actor in buffer:
                    works = actor.get("works")
                    if works:
                        grouped = {}
                        filtered = [
                            w for w in works
                            if not (isinstance(w.get("media"), str) and _normalize_media(w.get("media")) in exclude_set)
                        ]
                        for w in filtered:
                            media = w.get("media", "Unknown")
                            entry = {k: v for k, v in w.items() if k != "media"}
                            grouped.setdefault(media, []).append(entry)
                        actor["works"] = [{"media": m, "credits": c} for m, c in grouped.items()]
                    # write actor JSON into stream, pretty-print
                    actor_json = json.dumps(actor, ensure_ascii=False, indent=2)
                    indented = '\n'.join('  ' + l for l in actor_json.splitlines())
                    if not first:
                        outfh.write(",\n")
                    outfh.write(indented)
                    # show progress: output completed actor name to stdout
                    print(actor.get("name", ""), flush=True)
                    first = False
                outfh.flush()
                buffer.clear()

            # close array and object
            outfh.write("\n]}\n")

    except FileNotFoundError:
        print(f"Input file not found: {args.path}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Error opening or processing input file: {e}", file=sys.stderr)
        # leave tmp for inspection; do not overwrite original output
        sys.exit(1)

    # atomically replace output with tmp
    try:
        os.replace(tmp, args.output)
    except Exception as e:
        print(f"Error replacing output file {args.output}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
