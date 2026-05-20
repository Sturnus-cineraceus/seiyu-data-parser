import argparse
from .io import open_bz2
from .wikistream import iter_pages
from . import extract

def parse_args():
    parser = argparse.ArgumentParser(description="seiyu data parser")
    parser.add_argument("path", help="Path to .bz2 file (Wikipedia multistream dump)")
    parser.add_argument("--limit", type=int, default=100, help="Max number of pages to scan and max number of matching pages to output")
    return parser.parse_args()

def main():
    args = parse_args()
    output_count = 0
    scanned = 0
    max_scan = args.limit
    max_output = args.limit
    with open_bz2(args.path) as fh:
        for page_xml in iter_pages(fh):
            scanned += 1
            title, cats = extract.extract_title_and_categories(page_xml)
            if cats:
                print(f"{title}\t{','.join(cats)}")
                output_count += 1
                if output_count >= max_output:
                    break
            if scanned >= max_scan:
                break

if __name__ == "__main__":
    main()