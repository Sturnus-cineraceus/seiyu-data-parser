import re
import xml.etree.ElementTree as ET
from typing import Tuple, List, Optional, Dict, Any
from . import template_extract

TARGET_CATEGORIES = [
    "日本の男性声優",
    "日本の女性声優",
]


def _build_section_header_re(section_name: str) -> re.Pattern:
    """
    Build a section-header regex for target names.
    """
    names = [section_name]
    if section_name in {"出演", "出演作品"}:
        # Some pages use alternate headers for voice-actor credits or works listings.
        names.extend(["出演（声優）", "出演(声優)", "出演作品"])
    name_pattern = "|".join(re.escape(n) for n in dict.fromkeys(names))
    return re.compile(r'(?m)^(?P<underline>={2,})\s*(?:' + name_pattern + r')\s*(?P=underline)\s*$')

def extract_title_and_categories(page_xml: str) -> Tuple[str, List[str], str]:
    """
    Robustly parse a <page> XML string and return (title, [matched category names], text).
    Handles XML namespaces by matching local-name of tags.
    Returns the page text as the third element to allow downstream template parsing.
    """
    try:
        root = ET.fromstring(page_xml)
    except ET.ParseError:
        return ("", [], "")
 
    title = ""
    text = ""
    # find title and text elements by local-name to avoid namespace issues
    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1] if "}" in elem.tag else elem.tag
        if tag == "title" and elem.text:
            title = elem.text.strip()
        elif tag == "text" and elem.text:
            text = elem.text
 
    matched: List[str] = []
    for cat in TARGET_CATEGORIES:
        if f"[[Category:{cat}" in text:
            matched.append(cat)
    return title, matched, text

def extract_section(page_xml: str, section_name: str = "出演") -> Tuple[str, int]:
    """
    Extract the raw wiki-markup text under a top-level section header like:
    == 出演 ==
    Returns the section body as-is (may contain templates, links, lists), or
    an empty string if the section is not present.
    """
    try:
        root = ET.fromstring(page_xml)
    except ET.ParseError:
        return "", 0
    text = ""
    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1] if "}" in elem.tag else elem.tag
        if tag == "text" and elem.text:
            text = elem.text
            break
    if not text:
        return "", 0
    # Find the section header at any level (>=2). Capture its level (number of '=').
    header_re = _build_section_header_re(section_name)
    m = header_re.search(text)
    if not m:
        return "", 0
    level = len(m.group('underline'))
    start = m.end()
    # Find the next header with the same level to bound the section, if any
    next_re = re.compile(r'(?m)^[=]{' + str(level) + r'}\s.*[=]{' + str(level) + r'}\s*$')
    nm = next_re.search(text, start)
    body = text[start:nm.start()] if nm else text[start:]
    return body, level


def parse_voice_template(page_input: str) -> Optional[Dict[str, Any]]:
    """
    Accept either a page XML string or raw wiki markup text.
    If an XML <page> is provided, extract the text element; otherwise treat input as raw text.
    Returns a dict with template fields (may include inferred birth_date/death_date/agency/official_site) or None.
    """
    # extract raw wikitext
    text = ""
    if isinstance(page_input, str) and ("<page" in page_input or "<text" in page_input or page_input.strip().startswith("<?xml")):
        try:
            root = ET.fromstring(page_input)
            for elem in root.iter():
                tag = elem.tag.rsplit("}", 1)[-1] if "}" in elem.tag else elem.tag
                if tag == "text" and elem.text:
                    text = elem.text
                    break
        except ET.ParseError:
            text = page_input
    else:
        text = page_input or ""

    if not text:
        return None

    # try using existing template extractor if available
    templates = []
    try:
        templates = template_extract.extract_voice_actor_dicts(text) or []
    except Exception:
        templates = []

    # pick candidate template (first with useful fields, else first)
    candidate = None
    for tpl in templates:
        if tpl and (tpl.get("name") or tpl.get("furigana") or tpl.get("agency") or tpl.get("official_site")):
            candidate = tpl
            break
    if candidate is None and templates:
        candidate = templates[0]

    # helper: parse raw {{声優 ...}} block to extract missing fields
    def _parse_raw_voice_template_block(wikitext: str) -> Dict[str, str]:
        """
        Find the full {{声優 ... }} block using balanced-brace scanning to tolerate nested templates,
        then extract lines of the form "| key = value" into a dict.
        """
        out: Dict[str, str] = {}
        if not wikitext:
            return out
        start_idx = wikitext.find("{{声優")
        if start_idx == -1:
            return out
        # scan forward to find matching closing "}}", accounting for nested {{ }}
        i = start_idx
        depth = 0
        end_idx = -1
        L = len(wikitext)
        while i < L - 1:
            if wikitext[i:i+2] == "{{":
                depth += 1
                i += 2
                continue
            if wikitext[i:i+2] == "}}":
                depth -= 1
                i += 2
                if depth == 0:
                    end_idx = i
                    break
                continue
            i += 1
        if end_idx == -1:
            # fallback: try a permissive regex if balancing failed
            m = re.search(r'\{\{声優[\s\S]*?\}\}', wikitext, flags=re.S)
            if not m:
                return out
            block = m.group(0)
        else:
            block = wikitext[start_idx:end_idx]

        # split lines and extract "| key = value"
        for line in block.splitlines():
            lm = re.match(r'^\s*\|\s*([^=|]+?)\s*=\s*(.*)$', line)
            if not lm:
                continue
            key = lm.group(1).strip()
            val = lm.group(2).strip()
            # remove trailing template closers carefully
            val = re.sub(r'\}\}\s*$', '', val).strip()
            out[key] = val
        return out

    # attempt to fill missing fields from raw block
    raw_fields = _parse_raw_voice_template_block(text)

    def _unwrap_url(s: Optional[str]) -> str:
        # [https://example.com Label] or plain url
        if not s:
            return ""
        m = re.search(r'\[?(https?://[^\s\]\)]+)', s)
        return m.group(1) if m else ""

    def _unwrap_wikilink(s: Optional[str]) -> str:
        # [[Name|Label]] or [[Name]]
        s = s or ""
        m = re.search(r'\[\[([^|\]]+)(?:\|([^]]+))?\]\]', s)
        if m:
            # prefer displayed label when present
            label_or_name = m.group(2) if m.group(2) else m.group(1)
            return template_extract.strip_markup(label_or_name) or ""
        return template_extract.strip_markup(s) or ""

    # build result starting from candidate if any
    result: Dict[str, Any] = {}
    if candidate and isinstance(candidate, dict):
        result.update(candidate)

    # fill name/furigana from raw if missing
    if (not result.get("name")) and raw_fields.get("名前"):
        result["name"] = re.sub(r'\s+', ' ', _unwrap_wikilink(raw_fields.get("名前")))
    if (not result.get("furigana")) and raw_fields.get("ふりがな"):
        result["furigana"] = re.sub(r'\s+', ' ', raw_fields.get("ふりがな") or "")

    # birth date: prefer direct field, else combine 生年/生月/生日
    if not result.get("birth_date"):
        if raw_fields.get("生年月日"):
            bd = raw_fields.get("生年月日")
            result["birth_date"] = re.sub(r'\s+', ' ', bd or "")
        else:
            y = raw_fields.get("生年") or raw_fields.get("年")
            mth = raw_fields.get("生月") or raw_fields.get("月")
            d = raw_fields.get("生日") or raw_fields.get("日")
            if y:
                try:
                    yv = int(re.sub(r'\D', '', y))
                    mv = int(re.sub(r'\D', '', mth)) if mth else 1
                    dv = int(re.sub(r'\D', '', d)) if d else 1
                    result["birth_date"] = f"{yv:04d}-{mv:02d}-{dv:02d}"
                except Exception:
                    # fallback to concatenated raw
                    parts = [p for p in (y, mth, d) if p]
                    if parts:
                        result["birth_date"] = '-'.join(parts)

    # death date: combine 没年/没月/没日 when all parts exist
    if not result.get("death_date"):
        y = raw_fields.get("没年")
        mth = raw_fields.get("没月")
        d = raw_fields.get("没日")
        if y and mth and d:
            try:
                yv = int(re.sub(r'\D', '', y))
                mv = int(re.sub(r'\D', '', mth))
                dv = int(re.sub(r'\D', '', d))
                result["death_date"] = f"{yv:04d}-{mv:02d}-{dv:02d}"
            except Exception:
                parts = [p for p in (y, mth, d) if p]
                if len(parts) == 3:
                    result["death_date"] = '-'.join(parts)

    # agency
    if not result.get("agency"):
        if raw_fields.get("事務所"):
            result["agency"] = _unwrap_wikilink(raw_fields.get("事務所"))
        elif raw_fields.get("所属"):
            result["agency"] = _unwrap_wikilink(raw_fields.get("所属"))

    # official site
    if not result.get("official_site") and raw_fields.get("公式サイト"):
        # value may be like: [https://... Label] or just URL or single bracket
        url = _unwrap_url(raw_fields.get("公式サイト"))
        if url:
            result["official_site"] = url

    # final normalization: normalize furigana (collapse spaces) and sanitize suspicious values
    if result.get("furigana"):
        result["furigana"] = re.sub(r'\s+', ' ', result["furigana"]).strip()
        # discard if value looks like another field or contains '|' or '=' or image/file keywords
        if re.search(r'[=\|]|画像|ファイル', result["furigana"]):
            result.pop("furigana", None)

    result = {k: v for k, v in result.items() if v is not None}
    return result if result else None


def parse_appearances(page_input: str, section_name: str = "出演") -> List[Dict[str, Any]]:
    """
    Accept either a page XML string or raw wiki markup text and return parsed works list.
    Uses existing extract_section + parse_works_section when input is XML; falls back to
    extracting the section directly from raw text when given plain wikitext.
    """
    text = ""
    # if xml-like, extract <text>
    if isinstance(page_input, str) and ("<page" in page_input or "<text" in page_input or page_input.strip().startswith("<?xml")):
        try:
            root = ET.fromstring(page_input)
            for elem in root.iter():
                tag = elem.tag.rsplit("}", 1)[-1] if "}" in elem.tag else elem.tag
                if tag == "text" and elem.text:
                    text = elem.text
                    break
        except ET.ParseError:
            text = page_input
    else:
        text = page_input or ""

    if not text:
        return []

    # reuse existing section extraction logic but on raw text
    header_re = _build_section_header_re(section_name)
    m = header_re.search(text)
    if not m:
        return []
    level = len(m.group('underline'))
    start = m.end()
    next_re = re.compile(r'(?m)^[=]{' + str(level) + r'}\s.*[=]{' + str(level) + r'}\s*$')
    nm = next_re.search(text, start)
    body = text[start:nm.start()] if nm else text[start:]
    return parse_works_section(body, parent_level=level)

def _clean_text(s: str) -> str:
    import html
    if not s:
        return ""
    # unescape first so escaped tags become matchable
    try:
        s = html.unescape(s)
    except Exception:
        pass
    # remove <ref ...>...</ref> and self-closing <ref/>
    s = re.sub(r'<ref\b[^>]*?>.*?</ref>|<ref\b[^>]*/?>', '', s, flags=re.S | re.I)
    # remove templates like {{...}}, including nested forms
    s = template_extract.strip_templates(s) or ""
    # remove bold/italic markup
    s = re.sub(r"'{2,}", '', s)
    # remove any remaining HTML tags
    s = re.sub(r'<[^>]+>', '', s)
    # remove isolated 'ref' tokens and stray angle brackets
    s = re.sub(r'\bref\b', '', s, flags=re.I)
    s = s.replace('<', '').replace('>', '')
    # final unescape and collapse whitespace
    try:
        s = html.unescape(s)
    except Exception:
        pass
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


# media normalization moved to src.seiyu_data_parser.media

_link_re = re.compile(r'\[\[([^|\]]+?)(?:\|([^]]+?))?\]\]')

# 役名の先頭に付く「主演・」等の表記を除去するための正規化用正規表現（先頭のみ）
# 注: 「助演」は現データで出現しないとのことなので対象外とする
ROLE_PREFIX_RE = re.compile(r'^(?:主演)\s*[・:：]\s*')

def _unwrap_links(s: str) -> str:
    return _link_re.sub(lambda m: (m.group(2) or m.group(1)).strip(), s)

def _extract_unwrapped_and_link(s: str):
    """
    Return (unwrapped_text, first_link_target_or_empty).
    For the first wiki link, capture the left side as the link target.
    The unwrapped_text uses display text when present.
    """
    first_link = None
    def repl(m):
        nonlocal first_link
        target = m.group(1).strip()
        label = (m.group(2) or target).strip()
        if first_link is None:
            first_link = target
        return label
    unwrapped = _link_re.sub(repl, s)
    return unwrapped, first_link or ""

def _split_media_blocks(text: str, parent_level: int | None = None):
    """
    Return list of (media_name, block_text). If no level-3+ headings found,
    return a single block with media "出演".
    """
    # Find all headings with level >= 3 and record their level and positions.
    blocks = []
    # If a parent_level is provided (level of the containing '出演' header),
    # treat media headings as one deeper than that (出演_level + 1).
    if parent_level is not None and parent_level > 0:
        media_level = parent_level + 1
        heading_re = re.compile(r'(?m)^(?P<underline>={' + str(media_level) + r'})\s*(?P<media>[^=]+?)\s*(?P=underline)\s*$')
        matches = list(heading_re.finditer(text))
        if not matches:
            # No media-level headings: treat whole section as '出演'
            if text.strip():
                blocks.append(("出演", text))
            return blocks
        last_pos = 0
        last_media = None
        for m in matches:
            if last_media is None:
                before = text[last_pos:m.start()]
                if before.strip():
                    blocks.append(("出演", before))
            else:
                blocks.append((last_media, text[last_pos:m.start()]))
            last_media = m.group('media').strip()
            last_pos = m.end()
        # append tail
        if last_media is None:
            if text.strip():
                blocks.append(("出演", text))
        else:
            blocks.append((last_media, text[last_pos:]))
        return blocks

    # Fallback: no parent_level provided — preserve previous behavior (use minimal heading level >=3)
    heading_re = re.compile(r'(?m)^(?P<underline>={3,})\s*(?P<media>[^=]+?)\s*(?P=underline)\s*$')
    matches = list(heading_re.finditer(text))
    if not matches:
        if text.strip():
            blocks.append(("出演", text))
        return blocks
    levels = [len(m.group('underline')) for m in matches]
    min_level = min(levels)
    last_pos = 0
    last_media = None
    for m in matches:
        level = len(m.group('underline'))
        name = m.group('media').strip()
        if level == min_level:
            if last_media is None:
                before = text[last_pos:m.start()]
                if before.strip():
                    blocks.append(("出演", before))
            else:
                blocks.append((last_media, text[last_pos:m.start()]))
            last_media = name
            last_pos = m.end()
        else:
            continue
    if last_media is None:
        if text.strip():
            blocks.append(("出演", text))
    else:
        blocks.append((last_media, text[last_pos:]))
    return blocks

def _parse_item_line(line: str):
    """
    Parse a single list item line (already cleaned and unwrapped links).
    Returns (title, [roles]).
    """
    line = line.strip()
    # remove trailing note markers like "※田中雪弥名義"
    line = re.sub(r'\s*※.*$', '', line).strip()
    suffix_delim_re = re.compile(r'(?:(?<=\s)|(?<=[\)）]))[-–—]\s*')

    def _top_level_suffix_delims(s: str):
        """Return suffix-delimiter matches that are not inside ()/（） groups."""
        matches = []
        depth = 0
        for m in suffix_delim_re.finditer(s):
            seg = s[:m.start()]
            depth = 0
            for ch in seg:
                if ch in '（(':
                    depth += 1
                elif ch in '）)' and depth > 0:
                    depth -= 1
            if depth == 0:
                matches.append(m)
        return matches

    def _strip_aggregate_suffix(s: str) -> str:
        # Drop trailing aggregate notes like "- 3シリーズ" or
        # "- 1シリーズ + 特別編2作品" while keeping ordinary titles intact.
        unit = r'(?:\d+\s*(?:シリーズ|作品|部作)|(?:シリーズ|作品|部作)|特別編\s*\d*\s*作品?|特別編|特別版\s*\d*\s*作品?|特別版)'
        # Accept optional parenthesized qualifiers attached to each aggregate unit,
        # e.g. "1作品(OAD)+1シリーズ(ODS上映)".
        unit_with_note = rf'{unit}(?:\s*[（(][^()（）]{{1,40}}[)）])?'
        delim_matches = _top_level_suffix_delims(s)
        if not delim_matches:
            return s
        m = delim_matches[-1]
        tail = (s[m.end():] or '').strip()
        if re.fullmatch(rf'{unit_with_note}(?:\s*[\+＋]\s*{unit_with_note})*', tail):
            return s[:m.start()].rstrip()
        # Also strip aggregate count tails that are followed by note text,
        # e.g. "- 5シリーズ / 2015年に総集編...劇場上映".
        if re.match(rf'^{unit_with_note}(?:\s*[\+＋]\s*{unit_with_note})*\s*[\/／]\s*.+$', tail):
            if re.search(r'\d{4}年|テレビ|TV|放送|上映|公開|総集編|再編集|劇場', tail):
                return s[:m.start()].rstrip()
        return s

    def _strip_informational_suffix(s: str) -> str:
        # Drop non-role tail notes such as broadcast/distribution remarks.
        # Keep role-like tails (e.g. "- ヤスオ" or "- 主演・A 役") for fallback parsing.
        out = s
        while True:
            delim_matches = _top_level_suffix_delims(out)
            if not delim_matches:
                return out
            m = delim_matches[-1]
            tail = (out[m.end():] or '').strip()
            if not tail:
                return out
            if re.search(r'\b役\b|[\s　]役$', tail):
                return out
            if re.search(r'TV|テレビ|放送|再編集|未放送|BD|DVD|配信|第\d+巻|特別編|特別版|コミックス', tail):
                out = out[:m.start()].rstrip()
                continue
            if re.fullmatch(r'[\wぁ-んァ-ヶ一-龠・ー]{1,20}', tail):
                year_paren = re.search(r'[（(][^()（）]*\d{4}[^()（）]*[)）]', out)
                if year_paren:
                    # 括弧内に年以外のコンテンツ（役名・局名等）があれば役は括弧内に取得済みと判断し、
                    # 外側の短い語を情報注記として除去する。
                    # 括弧内が年・日付だけの場合は除去しない（外側が役名の可能性がある）。
                    inner = year_paren.group(0)[1:-1]
                    inner_clean = re.sub(r'\d+', '', inner)
                    inner_clean = re.sub(r'[年月日、,，\s\-–—~〜]+', '', inner_clean).strip()
                    if inner_clean:
                        out = out[:m.start()].rstrip()
                        continue
                return out
            return out

    line = _strip_aggregate_suffix(line)
    line = _strip_informational_suffix(line)

    def _looks_like_year_or_date_segment(s: str) -> bool:
        s = re.sub(r'\s+', '', s or '')
        if not s:
            return False
        return bool(
            re.fullmatch(r'\d{4}(?:年)?', s)
            or re.fullmatch(r'\d{4}(?:年)?[-–—~〜]\d{4}(?:年)?', s)
            or re.fullmatch(r'\d{4}(?:年)?[-–—~〜]', s)
            or re.fullmatch(r'\d{1,2}月(?:\d{1,2}日)?', s)
            or re.fullmatch(r'\d{1,2}日', s)
        )

    def _strip_episode_broadcast_suffix(s: str) -> str:
        # Trim trailing episode+broadcast metadata from title text, e.g.
        # "作品名 第21話（1996年7月19日、テレビ朝日）" -> "作品名".
        # Require a known broadcaster in parentheses to avoid over-stripping.
        broadcasters = r'(?:テレビ朝日|テレビ東京|フジテレビ|TBS|NHK|日本テレビ)'
        pat = re.compile(
            rf'\s*(?:第?\s*[0-9０-９]+\s*話)\s*[（(][^()（）]*{broadcasters}[^()（）]*[)）]\s*$'
        )
        return pat.sub('', s or '').strip()

    def _find_trailing_parenthesized_segment(s: str):
        s = (s or '').rstrip()
        if not s or s[-1] not in '）)':
            return None
        depth = 0
        for i in range(len(s) - 1, -1, -1):
            ch = s[i]
            if ch in '）)':
                depth += 1
            elif ch in '（(' and depth > 0:
                depth -= 1
                if depth == 0:
                    return i, len(s), s[i + 1:len(s) - 1]
        return None

    # Pick the right-most role-like parenthesized segment near the line tail.
    # This avoids consuming title-side parentheses such as "（第1作）" in link labels.
    selected = None
    trailing_par = _find_trailing_parenthesized_segment(line)
    if trailing_par:
        seg_start, seg_end, seg_text = trailing_par
        cand = re.sub(r'〈.*?〉', '', (seg_text or '')).strip()
        if cand and not _looks_like_year_or_date_segment(cand):
            selected = {"start": seg_start, "end": seg_end, "text": seg_text}

    if not selected:
        par_matches = list(re.finditer(r'[（(](.*?)[)）]', line))
        for m_par in reversed(par_matches):
            tail = (line[m_par.end():] or '').strip()
            # accept only trailing role segment: suffix must be empty or note marker
            if tail and not tail.startswith('※'):
                continue
            cand = (m_par.group(1) or '').strip()
            cand = re.sub(r'〈.*?〉', '', cand).strip()
            if not cand:
                continue
            if _looks_like_year_or_date_segment(cand):
                continue
            selected = {"start": m_par.start(), "end": m_par.end(), "text": m_par.group(1)}
            break

    if selected:
        par = (selected["text"] or '').strip()
        # Remove only the selected role segment and keep title-side parentheses intact.
        before = line[:selected["start"]].strip()
        after = line[selected["end"]:].strip()
        title = (before + after).strip()
    else:
        par = ''
        title = line

    roles = []
    # パターン2: 括弧内役名パターン
    # 説明: 項目の括弧内に年・局などの注記とともに役名が列挙されている場合の抽出ロジック。
    #        年・期間等を示す文字列（数字・年・ハイフンなど）を除外して役名候補を収集する。
    if par:
        # First split by comma-like delimiters to separate year-info from role names.
        # Preserve '・' (used inside names) and defer slash splitting until
        # after angle-bracket annotations are removed.
        parts = re.split(r'[、,，]+', par)
        for p in parts:
            p = p.strip()
            # Remove inline angle-bracket annotations (e.g. 〈第2話Aパート〉) before numeric checks
            p_clean = re.sub(r'〈.*?〉', '', p).strip()
            # Skip only explicit year/date-like segments; keep numeric role names (e.g. "009").
            if _looks_like_year_or_date_segment(p_clean):
                continue
            if not p_clean:
                continue
            # Further split on whitespace or slashes (but not '・') to handle cases like "役名 / 別名"
            subparts = re.split(r'[\/\s]+', p_clean)
            for sp in subparts:
                sp = sp.strip()
                if re.fullmatch(r'[-–—~〜]+', sp):
                    continue
                if sp:
                    roles.append(sp)
    # final cleanup of role entries
    roles = [r.strip(" \t\n\r'\"") for r in roles if r.strip()]

    # パターン1: 外側サフィックスパターン（優先度高）
    # 説明: タイトル部分にハイフン等で区切られ、その直後に「 役」が現れる場合は
    #        括弧内の注記ではなく外側の役表記を優先して抽出する。
    #        「役」の直後は行末・空白・区切り記号のみ許容し、'役人' 等を誤検出しない。
    m_role_suffix = re.search(
        r'(?:(?<=\s)|(?<=[\)）]))[-–—]\s*(.+?)\s+役(?=\s|$|[、,，/／\)\]\}\.\,\:\;\!\?])\s*$',
        title
    )
    if m_role_suffix:
        # 外側表記が見つかったら括弧内で得た roles を上書きする（外側優先）
        new_roles = []
        role_text = m_role_suffix.group(1).strip()
        for sp in re.split(r'[、,，/／]+', role_text):
            sp = sp.strip().strip(' \t\n\r\'"')
            if sp:
                new_roles.append(sp)
        roles = new_roles
        # タイトルからハイフン＋役部分を削除
        title = title[:m_role_suffix.start()].strip()
    else:
        # フォールバック: 行末のハイフン区切りで役名のみが付くケース（例: "作品 - ヤスオ"）
        if not roles:
            # Prefer the right-most delimiter so year ranges like "1998年 - 1999年" are not mistaken as role suffixes.
            delim_matches = _top_level_suffix_delims(title)
            for m_role_fallback in reversed(delim_matches):
                role_text = (title[m_role_fallback.end():] or '').strip()
                if not role_text:
                    continue
                # Avoid capturing cases where the suffix contains year-like or channel info (digits or 年)
                if re.search(r'\d|年', role_text):
                    continue
                # Generic aggregate words are not cast roles.
                if re.fullmatch(r'(?:シリーズ|作品|部作)', role_text):
                    continue
                new_roles = []
                for sp in re.split(r'[、,，/／]+', role_text):
                    sp = sp.strip().strip(' \t\n\r\'"')
                    if sp:
                        new_roles.append(sp)
                if new_roles:
                    roles = new_roles
                    title = title[:m_role_fallback.start()].strip()
                    break

    # 役名候補の正規化: 先頭の「主演・」表記があれば除去（助演は対象外）
    normalized = []
    for r in roles:
        nr = ROLE_PREFIX_RE.sub('', r).strip()
        prev = None
        while prev != nr:
            prev = nr
            nr = re.sub(r'[（(][^()（）]*[)）]', '', nr)
        nr = re.sub(r'\s+', ' ', nr).strip()
        if nr:
            normalized.append(nr)
    roles = normalized

    # Remove episode/broadcast metadata that should not be part of the work title.
    title = _strip_episode_broadcast_suffix(title)

    return title, roles

def parse_works_section(section_text: str, parent_level: int | None = None):
    """
    Parse the raw '出演' section text and return a list of works:
    [{"media": "...", "title": "...", "wiki_title": "...", "roles": ["r1","r2"], "year": 1979}, ...]
    The "year" field is an integer when present, otherwise an empty string "".

    Behavior change: if a media-level heading's name is a year (e.g. "2014年"), treat it as a year marker
    that applies to the most recent non-year media above it. Also detect year subheadings inside a media
    block (deeper-level headings) and apply those years to their contained items.
    """
    if not section_text:
        return []
    blocks = _split_media_blocks(section_text, parent_level=parent_level)
    # matches list item lines that start with one or more asterisks (allow leading spaces)
    item_re = re.compile(r'^\s*\*+\s*(.+)$')
    # old style table year lines like: | 1979年 |
    table_year_re = re.compile(r'^\|\s*(\d{4})\s*年')
    # heading-level year detection (e.g. '2014年' or '2014')
    heading_year_re = re.compile(r'^\s*(\d{4})\s*(?:年)?\s*$')

    results = []
    last_non_year_media = None
    # Determine media_level if parent_level provided
    media_level = (parent_level + 1) if (parent_level is not None and parent_level > 0) else None

    def _process_text_block(text_block: str, media_name: str, current_year: int | None):
        """Parse list-item lines in text_block and append to results using media_name and current_year."""
        def _extract_inline_year_from_title(text: str):
            """Extract trailing parenthesized year/year-range from title and return (stripped_title, year_or_none)."""
            t = (text or '').strip()
            # Accept both full-width and half-width parentheses at line tail.
            m = re.search(
                r'\s*[（(]\s*(\d{4})\s*(?:年)?\s*(?:[-–—~〜]\s*(\d{4})\s*(?:年)?)?\s*[)）]\s*$',
                t,
            )
            if not m:
                return t, None
            y = None
            try:
                y1 = int(m.group(1))
                y2 = int(m.group(2)) if m.group(2) else None
                y = min(y1, y2) if y2 is not None else y1
            except Exception:
                y = None
            t = (t[:m.start()] + t[m.end():]).strip()
            return t, y

        def _extract_inline_year_from_item_text(text: str):
            """Extract year/year-range from trailing parenthesized item text."""
            t = (text or '').strip()
            m = re.search(
                r'\s*[（(]\s*(\d{4})\s*(?:年)?\s*(?:[-–—~〜]\s*(\d{4})\s*(?:年)?)?\s*(?:[、,，][^()（）]*)?\s*[)）]\s*(?:[-–—].*)?$',
                t,
            )
            if m:
                try:
                    y1 = int(m.group(1))
                    y2 = int(m.group(2)) if m.group(2) else None
                    return min(y1, y2) if y2 is not None else y1
                except Exception:
                    return None

            # Support detailed date forms such as:
            # 「（1996年7月19日、テレビ朝日）」 or 「（1996年7月、テレビ朝日）」.
            m_tail_par = re.search(r'\s*[（(]([^()（）]+)[)）]\s*(?:[-–—].*)?$', t)
            if not m_tail_par:
                return None
            inner = (m_tail_par.group(1) or '').strip()
            m_year = re.search(r'(\d{4})\s*年', inner)
            if not m_year:
                m_year = re.search(r'(^|[^\d])(\d{4})(?!\d)', inner)
                if not m_year:
                    return None
                year_group = 2
            else:
                year_group = 1
            try:
                return int(m_year.group(year_group))
            except Exception:
                return None

        for line in text_block.splitlines():
            # detect table-style year rows
            m_year = table_year_re.match(line.strip())
            if m_year:
                try:
                    current_year = int(m_year.group(1))
                except Exception:
                    current_year = None
                continue
            m_item = item_re.match(line)
            if not m_item:
                continue
            raw = m_item.group(1)
            cleaned = _clean_text(raw)

            # enumerate all wiki links in the item as (target, label)
            item_link_pairs = [
                (m.group(1).strip(), (m.group(2) or m.group(1)).strip())
                for m in _link_re.finditer(cleaned)
            ]
            first_link_target = item_link_pairs[0][0] if item_link_pairs else ""

            # extract any link/label present in the media heading
            media_unwrapped, media_link = _extract_unwrapped_and_link(media_name)

            # unwrapped display text for the item (used to parse title/roles)
            unwrapped, _ = _extract_unwrapped_and_link(cleaned)
            if not unwrapped:
                continue
            # If the list item is a single wikilink only, parentheses in the label
            # are title-side qualifiers (e.g. "作品名（第2作）"), not cast roles.
            is_single_link_item = bool(re.fullmatch(r'\s*\[\[[^\]]+\]\]\s*', cleaned or ''))
            if is_single_link_item:
                title, roles = unwrapped.strip(), []
                m_title_qual = re.search(r'[（(]\s*([^()（）]+?)\s*[)）]\s*$', title)
                if m_title_qual:
                    qual = m_title_qual.group(1).strip()
                    if re.fullmatch(r'(?:第\d+\s*(?:作|期|部|章|シリーズ)|(?:テレビ|TV)?アニメ第\d+シリーズ)', qual):
                        title = title[:m_title_qual.start()].rstrip()
            else:
                title, roles = _parse_item_line(unwrapped)

            # Keep a fallback year from the original item text for cases where
            # _parse_item_line consumes parenthesized year+role segments.
            item_inline_year = _extract_inline_year_from_item_text(unwrapped)

            # Remove trailing year parenthesis from title, and use it as year only
            # when no year heading/table marker is already active.
            title, inline_year = _extract_inline_year_from_title(title)
            title = title.strip(" \t\n\r'\"")
            title = re.sub(r"'{2,}", '', title).strip()
            if not title:
                continue

            # Determine wiki_title with priority:
            # 1) If the media heading has a link and the item contains a link
            #    that matches the media link (by target or by label==media label), use it.
            # 2) If the media heading has a link, use that (block default).
            # 3) Use a link that matches the parsed title.
            # 4) Fallback to the parsed title.
            chosen = ""
            if media_link and item_link_pairs:
                for target, label in item_link_pairs:
                    if target == media_link or (media_unwrapped and label == media_unwrapped):
                        chosen = target
                        break
            if not chosen and media_link:
                chosen = media_link
            if not chosen and item_link_pairs:
                def _title_key(s: str) -> str:
                    s = (s or '').strip()
                    s = re.sub(r'\s*[（(][^()（）]*[)）]\s*$', '', s)
                    s = re.sub(r'\s+', ' ', s).strip()
                    return s

                title_key = _title_key(title)
                for target, label in item_link_pairs:
                    if title_key and (_title_key(target) == title_key or _title_key(label) == title_key):
                        chosen = target
                        break
            if not chosen:
                chosen = title

            wiki_title = chosen
            if current_year is not None:
                year_val = current_year
            elif inline_year is not None:
                year_val = inline_year
            elif item_inline_year is not None:
                year_val = item_inline_year
            else:
                year_val = ""
            # strip remaining markup from title, canonical_name and roles
            clean_title = template_extract.strip_markup(title) or ""
            clean_title = re.sub(r'[<>]', '', clean_title).strip()
            clean_title = re.sub(r'\bref\b', '', clean_title, flags=re.I).strip()
            clean_canonical = template_extract.strip_markup(wiki_title) or ""
            clean_canonical = re.sub(r'[<>]', '', clean_canonical).strip()
            clean_canonical = re.sub(r'\bref\b', '', clean_canonical, flags=re.I).strip()
            clean_roles = []
            for r in roles:
                if not r:
                    continue
                rr = template_extract.strip_markup(r)
                if not rr:
                    continue
                rr = re.sub(r'[<>]', '', rr).strip()
                rr = re.sub(r'\bref\b', '', rr, flags=re.I).strip()
                if rr:
                    clean_roles.append(rr)
            results.append({
                "media": media_name,
                "title": clean_title,
                "canonical_name": clean_canonical,
                "roles": clean_roles,
                "year": year_val
            })

    for media, block in blocks:
        # If the media heading itself is a year, use it as a year marker for the previous non-year media
        m_h_year = heading_year_re.match(media)
        if m_h_year:
            # this block likely contains items for the previous media, with this media heading being a year
            try:
                year_val = int(m_h_year.group(1))
            except Exception:
                year_val = None
            target_media = last_non_year_media or media
            _process_text_block(block, target_media, year_val)
            # do not update last_non_year_media
            continue

        # media is a normal media heading
        active_media = media
        last_non_year_media = media

        # If media_level is known, look for deeper-level subheadings inside this block (e.g. year subheadings)
        if media_level is not None:
            # subheadings are level >= media_level+1
            sub_re = re.compile(r'(?m)^(?P<underline>={' + str(media_level + 1) + r',})\s*(?P<name>[^=]+?)\s*(?P=underline)\s*$')
            matches = list(sub_re.finditer(block))
            if not matches:
                # no subheadings, process whole block under active_media
                _process_text_block(block, active_media, None)
                continue
            # iterate segments split by subheadings
            last_pos = 0
            current_year = None
            for m in matches:
                pre = block[last_pos:m.start()]
                if pre.strip():
                    _process_text_block(pre, active_media, current_year)
                sub_name = m.group('name').strip()
                m_sub_year = heading_year_re.match(sub_name)
                if m_sub_year:
                    try:
                        current_year = int(m_sub_year.group(1))
                    except Exception:
                        current_year = None
                else:
                    current_year = None
                last_pos = m.end()
            # tail
            tail = block[last_pos:]
            if tail.strip():
                _process_text_block(tail, active_media, current_year)
        else:
            # media_level unknown: fall back to simple processing
            _process_text_block(block, active_media, None)

    return results
