import argparse
import json
import os
import sys
import re
import html
from typing import Any, Dict, List
from .io import open_bz2
from .wikistream import iter_pages
from . import extract
from . import template_extract

from . import media

# normalization utilities to strip HTML comments, <ref> tags, templates, and HTML entities
_comment_re = re.compile(r'<!--.*?-->|<!--.*', re.S)
_ref_re = re.compile(r'<ref\\b[^>]*?>.*?</ref>|<ref\\b[^>]*?>.*', re.S | re.I)
_ref_self_re = re.compile(r'<ref\\b[^>]*/>', re.I)
_tag_re = re.compile(r'<[^>]+>')
_template_re = re.compile(r'{{.*?}}', re.S)

def normalize_text(s: str) -> str:
    if not s or not isinstance(s, str):
        return s
    prev = None
    while s != prev:
        prev = s
        s = html.unescape(s)
    s = _ref_re.sub('', s)
    s = _ref_self_re.sub('', s)
    s = _comment_re.sub('', s)
    s = _template_re.sub('', s)
    s = _tag_re.sub('', s)
    s = html.unescape(s)
    s = s.replace('->', '')
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def normalize_value(v):
    if isinstance(v, str):
        return normalize_text(v)
    if isinstance(v, dict):
        return {k: normalize_value(val) for k, val in v.items()}
    if isinstance(v, list):
        return [normalize_value(x) for x in v]
    return v

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
    parser.add_argument("--limit", type=int, default=None, help="Max number of pages to scan and max number of matching pages to output. If omitted, process all pages.")
    parser.add_argument("--output", "-o", default="voice_actor.json", help="Output JSON file path (default: ./voice_actor.json)")
    return parser.parse_args()

def main():
    args = parse_args()
    # verify input file exists before attempting to open
    if not os.path.exists(args.path):
        print(f"Input file not found: {args.path}", file=sys.stderr)
        sys.exit(2)
    output_count = 0
    scanned = 0
    max_scan = args.limit if args.limit is not None else float('inf')
    max_output = args.limit if args.limit is not None else float('inf')

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
                title, cats, page_text = extract.extract_title_and_categories(page_xml)
                if cats:
                    # parse template and appearances separately and combine simply
                    tpl = extract.parse_voice_template(page_xml)
                    works = extract.parse_appearances(page_xml, section_name="出演")
                    result_item: Dict[str, Any] = {
                        "name": _strip_parenthetical(title),
                        "canonical_name": title,
                    }
                    if tpl:
                        for k in ("furigana", "birth_date", "agency", "official_site"):
                            if tpl.get(k):
                                result_item[k] = tpl.get(k)
                    if works:
                        result_item["works"] = works

                    # append to buffer and flush if needed
                    buffer.append(result_item)
                    output_count += 1

                    if len(buffer) >= BATCH_SIZE:
                        # prepare grouped entries and write batch
                        for actor in buffer:
                            # centralize media normalization/filtering/grouping
                            actor = media.process_actor(actor)
                            # normalize actor strings to remove comments/ref tags before dumping
                            actor = normalize_value(actor)
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
                for actor in buffer:
                    actor = media.process_actor(actor)
                    # normalize actor strings to remove comments/ref tags before dumping
                    actor = normalize_value(actor)
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