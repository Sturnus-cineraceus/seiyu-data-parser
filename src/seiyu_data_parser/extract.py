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
