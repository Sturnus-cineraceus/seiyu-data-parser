#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
from typing import Optional, Dict, Any, List

TEMPLATE_RE = re.compile(r'\{\{声優(.*?)\}\}', re.S)
FIELD_RE = re.compile(r'^\s*\|\s*([^=|]+?)\s*=\s*(.+)$', re.M)
LINK_RE = re.compile(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]')
URL_BRACKET_RE = re.compile(r'\[([^ ]+)(?: [^\]]+)?\]')
TAG_RE = re.compile(r'<ref.*?>.*?</ref>|<br\s*/?>', re.S)

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
    s = TAG_RE.sub('', s)
    s = re.sub(r'\{\{.*?\}\}', '', s)
    s = LINK_RE.sub(r'\\1', s)
    s = s.strip()
    return s

def parse_birth(fields: Dict[str, str]) -> Optional[str]:
    year = fields.get('生年') or fields.get('生年 ')
    month = fields.get('生月') or fields.get('生月 ')
    day = fields.get('生日') or fields.get('生日 ')
    try:
        y = int(year)
        m = int(month)
        d = int(day)
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
        agency = strip_markup(t.get('事務所'))
        site = t.get('公式サイト')
        if site:
            m = URL_BRACKET_RE.search(site)
            site = m.group(1) if m else site.strip()
        out.append({
            'name': name,
            'furigana': furigana,
            'birth_date': birth,
            'agency': agency,
            'official_site': site
        })
    return out