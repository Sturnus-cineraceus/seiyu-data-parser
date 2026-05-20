import argparse
from .io import open_bz2
from .wikistream import iter_pages


def parse_args():
    parser = argparse.ArgumentParser(description="seiyu data parser")
    parser.add_argument("path", help="Path to .bz2 file (Wikipedia multistream dump)")
    parser.add_argument("--limit", type=int, default=100, help="Max number of <page> elements to output")
    return parser.parse_args()


def main():
    args = parse_args()
    with open_bz2(args.path) as fh:
        for i, page_xml in enumerate(iter_pages(fh)):
            # page_xml is a unicode string containing the <page> element
            print(page_xml)
            if i + 1 >= args.limit:
                break


if __name__ == "__main__":
    main()