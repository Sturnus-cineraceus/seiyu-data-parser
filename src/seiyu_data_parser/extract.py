import re
import xml.etree.ElementTree as ET
from typing import Tuple, List

TARGET_CATEGORIES = [
    "日本の男性声優",
    "日本の女性声優",
]

def extract_title_and_categories(page_xml: str) -> Tuple[str, List[str]]:
    """
    Robustly parse a <page> XML string and return (title, [matched category names]).
    Handles XML namespaces by matching local-name of tags.
    """
    try:
        root = ET.fromstring(page_xml)
    except ET.ParseError:
        return ("", [])

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
    return title, matched

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
    """
    if not section_text:
        return []
    blocks = _split_media_blocks(section_text, parent_level=parent_level)
    # matches list item lines that start with one or more asterisks (allow leading spaces)
    item_re = re.compile(r'^\s*\*+\s*(.+)$')
    year_re = re.compile(r'^\|\s*(\d{4})\s*年')
    results = []
    for media, block in blocks:
        # media normalization moved to media module; keep raw heading here
        current_year = None
        for line in block.splitlines():
            # detect year-def lines like: | 1979年 |
            m_year = year_re.match(line.strip())
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
            # clean refs/templates/formatting
            cleaned = _clean_text(raw)
            # unwrap wiki links and extract first link target
            unwrapped, link = _extract_unwrapped_and_link(cleaned)
            if not unwrapped:
                continue
            title, roles = _parse_item_line(unwrapped)
            # remove emphasis markup leftovers and stray punctuation
            title = title.strip(" \t\n\r'\"")
            title = re.sub(r"'{2,}", '', title).strip()
            # ignore empty titles
            if not title:
                continue
            wiki_title = link or title
            year_val = current_year if current_year is not None else ""
            results.append({
                "media": media,
                "title": title,
                "wiki_title": wiki_title,
                "roles": roles,
                "year": year_val
            })
    return results
