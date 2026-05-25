"""Centralized media normalization and filtering for seiyu-data-parser.

Expose process_actor(actor: dict) which normalizes media headings, filters out excluded media,
and groups works into [{'media': ..., 'credits': [...]}, ...] to match existing output format.
"""
from typing import Dict, Any, List
import re

DEFAULT_EXCLUDE_MEDIA = [
    "バラエティ",
    "イベント",
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
]


def _normalize_media(s: str) -> str:
    if not isinstance(s, str):
        return ""
    m = s
    m = re.sub(r'<.*?>', '', m)
    m = re.sub(r'\{\{.*?\}\}', '', m, flags=re.S)
    m = m.replace('、', ',').replace('　', ' ').strip()
    if '特撮' in m or '特攝' in m:
        return '特撮'
    if 'CM' in m or 'ＣＭ' in m:
        return 'CM'
    m = m.replace('バラエティー', 'バラエティ')
    if 'バラエティ' in m:
        return 'バラエティ'
    m = m.replace('ナレーター', 'ナレーション')
    if 'ナレーション' in m:
        return 'ナレーション'
    if 'イベント' in m:
        return 'イベント'
    m = m.replace('パチスロー', 'パチスロ')
    m = m.replace('パチンコー', 'パチンコ')
    if 'パチスロ' in m or 'スロット' in m:
        return 'パチスロ'
    if 'パチンコ' in m:
        return 'パチンコ'
    if 'ゲーム' in m:
        return 'ゲーム'
    return m


EXCLUDE_MEDIA_SET = frozenset(_normalize_media(m) for m in DEFAULT_EXCLUDE_MEDIA)

# Additional exclude substrings/patterns for fuzzy matching (compiled for performance).
EXCLUDE_SUBSTRINGS = ("バラエティ", "パチスロ", "スロット", "パチンコ", "イベント")
# Build regexes that try to match tokens as standalone or separated by punctuation/space.
# This reduces false positives from accidental substrings.
_EX_CHAR_CLASS = r'[^0-9A-Za-zぁ-んァ-ヶ一-龠]'
EXCLUDE_REGEXES = [re.compile(rf'(^|{_EX_CHAR_CLASS}){re.escape(tok)}($|{_EX_CHAR_CLASS})') for tok in EXCLUDE_SUBSTRINGS]



def process_actor(actor: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize, filter and group works for a single actor record.

    Input actor: {"name": ..., "wiki_title": ..., "works": [ {"media": raw, "title":..., ...}, ... ]}
    Output actor has works grouped as [{"media": normalized_media, "credits": [...]}, ...].
    """
    if not isinstance(actor, dict):
        return actor
    works = actor.get("works")
    if not isinstance(works, list):
        return actor

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for w in works:
        if not isinstance(w, dict):
            continue
        media_raw = w.get("media")
        nm = _normalize_media(media_raw) if isinstance(media_raw, str) else ""
        # Skip excluded media by exact normalized set or by regex patterns to avoid false positives.
        if nm in EXCLUDE_MEDIA_SET:
            continue
        if any(rx.search(nm) for rx in EXCLUDE_REGEXES):
            continue
        media_key = nm or (media_raw or "Unknown")
        entry = {k: v for k, v in w.items() if k != "media"}
        grouped.setdefault(media_key, []).append(entry)

    actor["works"] = [{"media": m, "credits": c} for m, c in grouped.items()]
    return actor
