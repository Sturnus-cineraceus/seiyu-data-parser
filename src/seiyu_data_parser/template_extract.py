#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import html
from typing import Optional, Dict, Any, List

TEMPLATE_RE = re.compile(r'\{\{声優(.*?)\}\}', re.S)
# Keep whitespace after '=' on the same line only; otherwise empty values can eat the next field line.
FIELD_RE = re.compile(r'^\s*\|\s*([^=|]+?)\s*=[ \t]*(.*)$', re.M)
LINK_RE = re.compile(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]')
URL_BRACKET_RE = re.compile(r'\[([^ ]+)(?: [^\]]+)?\]')
# robust ref/tag remover: handles attributes, self-closing refs, and <br />
TAG_RE = re.compile(r'<ref\b[^>]*?>.*?</ref>|<ref\b[^>]*/?>|<br\s*/?>', re.S | re.I)

def strip_templates(s: Optional[str]) -> Optional[str]:
    """Remove template blocks like {{...}}, including nested templates."""
    if s is None:
        return None
    out = s
    prev = None
    # Repeatedly remove innermost templates until stable.
    while out != prev:
        prev = out
        out = re.sub(r'\{\{[^{}]*\}\}', '', out)
    # Also drop malformed trailing fragments like "{{R|...".
    while True:
        cleaned = re.sub(r'\{\{[^{}]*$', '', out)
        if cleaned == out:
            break
        out = cleaned
    out = out.replace('}}', '')
    return out

def normalize_furigana(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = s.strip()
    # remove all internal whitespace (user requested)
    s = re.sub(r'\s+', '', s)
    return s

def strip_markup(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    # unescape HTML entities first so escaped tags become matchable
    try:
        s = html.unescape(s)
    except Exception:
        pass
    # remove ref blocks and simple <br/>
    s = TAG_RE.sub('', s)
    # remove templates like {{...}}, including nested forms
    s = strip_templates(s) or ""
    # unwrap external links [https://example.com Label] -> Label
    s = re.sub(r'\[(https?://[^\s\]]+)\s+([^\]]+)\]', r'\2', s)
    # unwrap bare external links [https://example.com] -> https://example.com
    s = re.sub(r'\[(https?://[^\s\]]+)\]', r'\1', s)
    # unwrap wikilinks [[A|B]] -> B
    s = LINK_RE.sub(r'\1', s)
    # remove any remaining HTML tags
    s = re.sub(r'<[^>]+>', '', s)
    # remove stray angle brackets and isolated 'ref' tokens
    s = s.replace('<', '').replace('>', '')
    s = re.sub(r'\bref\b', '', s, flags=re.I)
    # collapse whitespace and trim
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def parse_birth(fields: Dict[str, str]) -> Optional[str]:
    year = fields.get('生年') or fields.get('生年 ')
    month = fields.get('生月') or fields.get('生月 ')
    day = fields.get('生日') or fields.get('生日 ')
    if not year or not month or not day:
        return None
    try:
        y = int(re.sub(r'\D', '', str(year)))
        m = int(re.sub(r'\D', '', str(month)))
        d = int(re.sub(r'\D', '', str(day)))
        return f"{y:04d}-{m:02d}-{d:02d}"
    except Exception:
        return None

def parse_death(fields: Dict[str, str]) -> Optional[str]:
    year = fields.get('没年') or fields.get('没年 ')
    month = fields.get('没月') or fields.get('没月 ')
    day = fields.get('没日') or fields.get('没日 ')
    if not year or not month or not day:
        return None
    try:
        y = int(re.sub(r'\D', '', str(year)))
        m = int(re.sub(r'\D', '', str(month)))
        d = int(re.sub(r'\D', '', str(day)))
        return f"{y:04d}-{m:02d}-{d:02d}"
    except Exception:
        return None

def extract_templates(text: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for m in TEMPLATE_RE.finditer(text):
        block = m.group(1)
        fields: Dict[str, str] = {}
        for fm in FIELD_RE.finditer(block):
            key = fm.group(1).strip()
            val = fm.group(2).strip()
            fields[key] = val
        results.append(fields)
    return results

def extract_voice_actor_dicts(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    templates = extract_templates(text)
    for t in templates:
        name = strip_markup(t.get('名前'))
        furigana = normalize_furigana(t.get('ふりがな'))
        birth = parse_birth(t)
        death = parse_death(t)
        agency = strip_markup(t.get('事務所'))
        site = t.get('公式サイト')
        if site:
            m = URL_BRACKET_RE.search(site)
            site = m.group(1) if m else site.strip()
        actor = {
            'name': name,
            'furigana': furigana,
            'birth_date': birth,
            'death_date': death,
            'agency': agency,
            'official_site': site
        }
        out.append({k: v for k, v in actor.items() if v is not None})
    return out