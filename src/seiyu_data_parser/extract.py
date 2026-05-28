import re
import xml.etree.ElementTree as ET
from typing import Tuple, List, Optional, Dict, Any
from . import template_extract

TARGET_CATEGORIES = [
    "日本の男性声優",
    "日本の女性声優",
]

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
    header_re = re.compile(r'(?m)^(?P<underline>={2,})\s*' + re.escape(section_name) + r'\s*(?P=underline)\s*$')
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
    Returns a dict with template fields (may include inferred birth_date/agency/official_site) or None.
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
            return m.group(1).strip()
        return re.sub(r'[{}\[\]]', '', s).strip()

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
    header_re = re.compile(r'(?m)^(?P<underline>={2,})\s*' + re.escape(section_name) + r'\s*(?P=underline)\s*$')
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
    # remove ref tags
    s = re.sub(r'<ref.*?>.*?</ref>', '', s, flags=re.S)
    # remove bold/italic markup
    s = re.sub(r"'{2,}", '', s)
    # remove HTML tags
    s = re.sub(r'<.*?>', '', s)
    # remove simple templates (non-greedy)
    s = re.sub(r'\{\{.*?\}\}', '', s, flags=re.S)
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

    # Find the first parenthesized segment anywhere in the line (full-width and ASCII parens).
    m_par = re.search(r'[（(](.*?)[)）]', line)
    if m_par:
        par = (m_par.group(1) or '').strip()
        # Remove the parenthesized segment but keep text before and after it as the title.
        before = line[:m_par.start()].strip()
        after = line[m_par.end():].strip()
        title = (before + ' ' + after).strip()
    else:
        par = ''
        title = line

    roles = []
    # パターン2: 括弧内役名パターン
    # 説明: 項目の括弧内に年・局などの注記とともに役名が列挙されている場合の抽出ロジック。
    #        年・期間等を示す文字列（数字・年・ハイフンなど）を除外して役名候補を収集する。
    if par:
        # First split by comma-like delimiters to separate year-info from role names.
        # Preserve '・' (used inside names) by not splitting on it.
        parts = re.split(r'[、,，/／]+', par)
        for p in parts:
            p = p.strip()
            # Remove inline angle-bracket annotations (e.g. 〈第2話Aパート〉) before numeric checks
            p_clean = re.sub(r'〈.*?〉', '', p).strip()
            # Skip segments that look like years or ranges (contain digits, '年' or hyphen)
            if re.search(r'\d|年|-', p_clean):
                continue
            if not p_clean:
                continue
            # Further split on whitespace or slashes (but not '・') to handle cases like "役名 / 別名"
            subparts = re.split(r'[\/\s]+', p_clean)
            for sp in subparts:
                sp = sp.strip()
                if sp:
                    roles.append(sp)
    # final cleanup of role entries
    roles = [r.strip(" \t\n\r'\"") for r in roles if r.strip()]

    # パターン1: 外側サフィックスパターン（優先度高）
    # 説明: タイトル部分にハイフン等で区切られ、その直後に「 役」が現れる場合は
    #        括弧内の注記ではなく外側の役表記を優先して抽出する。
    #        「役」の直後は行末・空白・区切り記号のみ許容し、'役人' 等を誤検出しない。
    m_role_suffix = re.search(
        r'\s[-–—]\s*(.+?)\s+役(?=\s|$|[、,，/／\)\]\}\.\,\:\;\!\?])\s*$',
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
        m_role_fallback = re.search(r'\s[-–—]\s*(.+?)\s*$', title)
        if m_role_fallback:
            role_text = m_role_fallback.group(1).strip()
            # Avoid capturing cases where the suffix contains year-like or channel info (digits or 年)
            if not re.search(r'\d|年', role_text):
                new_roles = []
                for sp in re.split(r'[、,，/／]+', role_text):
                    sp = sp.strip().strip(' \t\n\r\'"')
                    if sp:
                        new_roles.append(sp)
                if new_roles:
                    roles = new_roles
                    title = title[:m_role_fallback.start()].strip()

    # 役名候補の正規化: 先頭の「主演・」表記があれば除去（助演は対象外）
    normalized = []
    for r in roles:
        nr = ROLE_PREFIX_RE.sub('', r).strip()
        if nr:
            normalized.append(nr)
    roles = normalized

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
            title, roles = _parse_item_line(unwrapped)
            title = title.strip(" \t\n\r'\"")
            title = re.sub(r"'{2,}", '', title).strip()
            if not title:
                continue

            # Determine wiki_title with priority:
            # 1) If the media heading has a link and the item contains a link
            #    that matches the media link (by target or by label==media label), use it.
            # 2) If the media heading has a link, use that (block default).
            # 3) Use the item's first link target.
            # 4) Fallback to the parsed title.
            chosen = ""
            if media_link and item_link_pairs:
                for target, label in item_link_pairs:
                    if target == media_link or (media_unwrapped and label == media_unwrapped):
                        chosen = target
                        break
            if not chosen and media_link:
                chosen = media_link
            if not chosen and first_link_target:
                chosen = first_link_target
            if not chosen:
                chosen = title

            wiki_title = chosen
            year_val = current_year if current_year is not None else ""
            results.append({
                "media": media_name,
                "title": title,
                "canonical_name": wiki_title,
                "roles": roles,
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
