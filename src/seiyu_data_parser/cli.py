import argparse
import os
from .io import open_bz2
from .wikistream import iter_pages
from . import extract

def parse_args():
    parser = argparse.ArgumentParser(description="seiyu data parser")
    parser.add_argument("path", help="Path to .bz2 file (Wikipedia multistream dump)")
    parser.add_argument("--limit", type=int, default=100, help="Max number of pages to scan and max number of matching pages to output")
    parser.add_argument("--unmatch-file", default="data/unmatched.txt", help="Path to write titles of pages that do NOT match the category criteria")
    return parser.parse_args()

def main():
    args = parse_args()
    output_count = 0
    scanned = 0
    max_scan = args.limit
    max_output = args.limit
    unmatched = []
    with open_bz2(args.path) as fh:
        for page_xml in iter_pages(fh):
            scanned += 1
            title, cats = extract.extract_title_and_categories(page_xml)
            if cats:
                # print only the title for matched pages
                print(title)
                output_count += 1
                if output_count >= max_output:
                    break
            else:
                if title:
                    unmatched.append(title)
            if scanned >= max_scan:
                break

    # write unmatched titles to file (one title per line)
    unmatch_path = args.unmatch_file
    os.makedirs(os.path.dirname(unmatch_path), exist_ok=True)
    with open(unmatch_path, "w", encoding="utf-8", newline="\n") as outfh:
        for t in unmatched:
            outfh.write(t + "\n")

if __name__ == "__main__":
    main()