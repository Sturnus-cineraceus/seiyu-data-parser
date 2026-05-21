import argparse
import json
import os
import sys
from .io import open_bz2
from .wikistream import iter_pages
from . import extract

def parse_args():
    parser = argparse.ArgumentParser(description="seiyu data parser")
    parser.add_argument("path", help="Path to .bz2 file (Wikipedia multistream dump)")
    parser.add_argument("--limit", type=int, default=100, help="Max number of pages to scan and max number of matching pages to output")
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
    max_scan = args.limit
    max_output = args.limit
    results = []
    try:
        with open_bz2(args.path) as fh:
            for page_xml in iter_pages(fh):
                scanned += 1
                title, cats = extract.extract_title_and_categories(page_xml)
                if cats:
                    # collect matched pages
                    results.append({"name": title, "wiki_title": title})
                    output_count += 1
                    if output_count >= max_output:
                        break
                if scanned >= max_scan:
                    break
    except FileNotFoundError:
        print(f"Input file not found: {args.path}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Error opening or processing input file: {e}", file=sys.stderr)
        sys.exit(1)
    # write JSON output
    try:
        with open(args.output, "w", encoding="utf-8") as outfh:
            json.dump(results, outfh, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error writing output file {args.output}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
