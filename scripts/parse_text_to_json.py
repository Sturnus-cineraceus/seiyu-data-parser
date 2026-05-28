#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import json
import re
import html
from typing import List, Dict, Any
import os as _os
import sys as _sys
# ensure package src/ is on sys.path when run from project root
_ROOT = _os.path.dirname(_os.path.dirname(__file__))
_SRC = _os.path.join(_ROOT, "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)
from seiyu_data_parser import extract

def write_json(path: str, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def sanitize_name(name: str) -> str:
    if not name:
        return ''
    return re.sub(r'[^\w\-]+', '_', name)

# remove HTML comments, <ref>...</ref> (including unterminated cases), self-closing <ref/> and other tags
_comment_re = re.compile(r'<!--.*?-->|<!--.*', re.S)
_ref_re = re.compile(r'<ref\b[^>]*?>.*?</ref>|<ref\b[^>]*?>.*', re.S | re.I)
_ref_self_re = re.compile(r'<ref\b[^>]*/>', re.I)
_tag_re = re.compile(r'<[^>]+>')
# simple non-nesting template removal (removes {{...}}); improves cleanliness but may be tuned
_template_re = re.compile(r'{{.*?}}', re.S)

def normalize_text(s: str) -> str:
    if not s or not isinstance(s, str):
        return s
    # repeatedly unescape until stable to handle nested/escaped entities
    prev = None
    while s != prev:
        prev = s
        s = html.unescape(s)
    # remove <ref> blocks (including unterminated), then self-closing refs
    s = _ref_re.sub('', s)
    s = _ref_self_re.sub('', s)
    # remove HTML comments (including unterminated)
    s = _comment_re.sub('', s)
    # remove simple templates like {{...}} (non-nesting)
    s = _template_re.sub('', s)
    # remove any remaining HTML-like tags
    s = _tag_re.sub('', s)
    # final unescape to convert entities like > -> >
    s = html.unescape(s)
    # remove common leftover arrow artifacts like "->" produced from >
    s = s.replace('->', '')
    # normalize whitespace
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

def main(argv: List[str] = None):
    argv = argv or sys.argv[1:]
    if len(argv) < 1:
        print("Usage: parse_text_to_json.py input.txt [output.json|outdir]")
        sys.exit(1)
    inp = argv[0]
    outp = argv[1] if len(argv) > 1 else None
    with open(inp, 'r', encoding='utf-8') as f:
        txt = f.read()
    # build entries by parsing the page text for template and appearances
    entries = []
    tpl = None
    try:
        tpl = extract.parse_voice_template(txt)
    except Exception:
        tpl = None
    works = []
    try:
        works = extract.parse_appearances(txt, section_name="出演")
    except Exception:
        works = []
    if tpl or works:
        entry = {
            "name": (tpl.get("name") if tpl and tpl.get("name") else None),
            "furigana": (tpl.get("furigana") if tpl and tpl.get("furigana") else None),
            "birth_date": (tpl.get("birth_date") if tpl and tpl.get("birth_date") else None),
            "agency": (tpl.get("agency") if tpl and tpl.get("agency") else None),
            "official_site": (tpl.get("official_site") if tpl and tpl.get("official_site") else None),
            "works": works
        }
        entries.append(entry)

    # normalize all string fields to strip HTML comments/tags and <ref> markers
    entries = [normalize_value(e) for e in entries]

    if outp:
        if os.path.isdir(outp):
            os.makedirs(outp, exist_ok=True)
            index = []
            for i, entry in enumerate(entries):
                name_safe = sanitize_name(entry.get('name') or f'entry_{i}')
                filename = f"{i:04d}_{name_safe}.json"
                path = os.path.join(outp, filename)
                write_json(path, entry)
                index.append({"file": filename, "name": entry.get('name')})
            write_json(os.path.join(outp, 'index.json'), index)
            print(f"Wrote {len(entries)} entries to directory {outp}")
        else:
            write_json(outp, entries)
            print(f"Wrote {len(entries)} entries to {outp}")
    else:
        print(json.dumps(entries, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()