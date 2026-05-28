#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, re
# ensure src on path
ROOT = os.path.dirname(os.path.dirname(__file__))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from seiyu_data_parser import template_extract, extract

def extract_section_from_wikitext(text: str, section_name: str = "出演"):
    header_re = re.compile(r'(?m)^(?P<underline>={2,})\s*' + re.escape(section_name) + r'\s*(?P=underline)\s*$')
    m = header_re.search(text)
    if not m:
        return "", 0
    level = len(m.group('underline'))
    start = m.end()
    next_re = re.compile(r'(?m)^[=]{' + str(level) + r'}\s.*[=]{' + str(level) + r'}\s*$')
    nm = next_re.search(text, start)
    body = text[start:nm.start()] if nm else text[start:]
    return body, level

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: inspect_test_page.py input.txt")
        sys.exit(1)
    path = sys.argv[1]
    txt = open(path, 'r', encoding='utf-8').read()
    print("=== Templates from {{声優}} ===")
    try:
        templates = template_extract.extract_voice_actor_dicts(txt)
    except Exception as e:
        print("template_extract error:", e)
        templates = []
    print(json.dumps(templates, ensure_ascii=False, indent=2))
    print("\n=== Extracted '出演' section (raw) ===")
    section, level = extract_section_from_wikitext(txt, "出演")
    print("level:", level)
    print(section[:1000])
    print("\n=== parse_works_section result (first 10) ===")
    try:
        works = extract.parse_works_section(section, parent_level=level)
    except Exception as e:
        print("parse_works_section error:", e)
        works = []
    print(json.dumps(works[:10], ensure_ascii=False, indent=2))