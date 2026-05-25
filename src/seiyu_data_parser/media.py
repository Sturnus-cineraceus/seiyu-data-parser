"""Centralized media normalization and filtering for seiyu-data-parser.

Expose process_actor(actor: dict) which normalizes media headings, filters out excluded media,
and groups works into [{'media': ..., 'credits': [...]}, ...] to match existing output format.
"""
from typing import Dict, Any, List
import re

# Exact normalized media strings to exclude (exact normalized match).
EXCLUDE_MEDIA_EXACT = [
    "バラエティ",
    "イベント",
    "ラジオ",
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
    # Note: tokens that should be matched by substring or bounded rules are defined below
]

# Tokens to match when they appear anywhere in the media string (substring match).
EXCLUDE_MEDIA_CONTAINS = (
    "テレビ",
    "バラエティ",
    "パチスロ",
    "スロット",
    "パチンコ",
    "イベント",
    "舞台",
    "ミュージカル",
    "ミュージック",
    "司会",
    "同人",
    "雑誌",
    "新聞",
    "小説",
    "広告",
    "アパレル",
    "アイドル",
    "アイスショー",
    "ライブ",
    "モデル",
    "実写",
    # Additional user-specified substring tokens to exclude (partial-match).
    "吹替",
    "吹き替え",
    "歌",
    "音楽",
    "ニュース",
    "プロモーション",
    "ユニット",
    "レコード",
    "公演",
    "振付",
    "携帯",
    "脚本",
    "演出",
    "連載",
    "コラム",
    "シングル",
    "スチル",
    "グラビア",
    "VP",
    "公式",
    "受賞",
)


def _normalize_media_initial(s: str) -> str:
    if not isinstance(s, str):
        return ""
    m = s
    m = re.sub(r'<.*?>', '', m)
    m = re.sub(r'\{\{.*?\}\}', '', m, flags=re.S)
    m = m.replace('、', ',').replace('　', ' ').strip()
    # normalize fullwidth CD to ASCII for matching
    m = m.replace('ＣＤ', 'CD')

    # Map TV anime variants to canonical 'アニメ' early so subsequent 'テレビ' exclusion
    # does not remove TV anime entries. Handle common variants like 'TVアニメ',
    # 'テレビアニメ', and 'テレビアニメーション'.
    if re.search(r'(?:TV|ＴＶ|テレビ)\s*アニメ', m):
        return 'アニメ'
    m = m.replace('テレビアニメーション', 'アニメ')
    m = m.replace('テレビアニメ', 'アニメ')
    m = m.replace('ＴＶアニメ', 'アニメ')
    m = m.replace('ＴＶアニメーション', 'アニメ')
    m = m.replace('TVアニメ', 'アニメ')
    m = m.replace('TVアニメーション', 'アニメ')

    # Map various audio-related variants to a single canonical media 'オーディオドラマ'.
    # Match common prefixes and tokens but avoid mapping lone 'CD' or generic 'ラジオ'.
    audio_tokens = [
        'オーディオドラマ', 'オーディオブック', 'オーディドラマ', 'オーディブック', 'オーディ',
        'ボイスドラマ', 'ボイスブック', 'ボイスCD', 'ボイスＣＤ',
        'カセットドラマ', 'カセットブック', 'カセット文庫', '朗読',
        'ドラマCD', 'ドラマＣＤ', 'ラジオドラマ'
    ]
    if any(tok in m for tok in audio_tokens):
        return 'オーディオドラマ'

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


def _normalize_media_final(s: str) -> str:
    if not isinstance(s, str):
        return ""
    m = s
    # Final normalization: canonicalize any media containing 'その他' to 'その他'
    if 'その他' in m:
        return 'その他'
    return m


# Derived exclusion helpers built from the canonical constant groups above.
# Exact normalized set for quick equality checks (use initial normalization here).
EXCLUDE_MEDIA_SET = frozenset(_normalize_media_initial(m) for m in EXCLUDE_MEDIA_EXACT)

# All tokens treated as substring (任意位置部分一致) for exclusion.
EXCLUDE_CONTAINS = tuple(EXCLUDE_MEDIA_CONTAINS)



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
        nm_initial = _normalize_media_initial(media_raw) if isinstance(media_raw, str) else ""
        # Exact normalized exclusion (first)
        if nm_initial in EXCLUDE_MEDIA_SET:
            continue
        # Substring exclusion against the initial normalized value (second)
        if any(tok in nm_initial for tok in EXCLUDE_CONTAINS):
            continue
        # Final normalization (e.g., map 'その他' to canonical 'その他')
        nm_final = _normalize_media_final(nm_initial) or (media_raw or "Unknown")
        media_key = nm_final
        entry = {k: v for k, v in w.items() if k != "media"}
        grouped.setdefault(media_key, []).append(entry)

    actor["works"] = [{"media": m, "credits": c} for m, c in grouped.items()]
    return actor
