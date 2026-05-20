import re
import xml.etree.ElementTree as ET
from typing import Tuple, List

TARGET_CATEGORIES = [
    "日本の男性声優",
    "日本の女性声優",
]

def extract_title_and_categories(page_xml: str) -> Tuple[str, List[str]]:
    """
    Parse a <page> XML string and return (title, [matched category names]).
    Matches if the page text contains '[[Category:日本の男性声優' or
    '[[Category:日本の女性声優' (allowing for pipes and extra text).
    """
    try:
        root = ET.fromstring(page_xml)
    except ET.ParseError:
        return ("", [])

    title_elem = root.find('title')
    title = (title_elem.text or "").strip() if title_elem is not None else ""

    text_elem = root.find('.//text')
    text = text_elem.text or "" if text_elem is not None else ""

    matched: List[str] = []
    for cat in TARGET_CATEGORIES:
        if f"[[Category:{cat}" in text:
            matched.append(cat)
    return title, matched