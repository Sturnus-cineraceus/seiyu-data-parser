import io
import xml.etree.ElementTree as ET
from typing import Iterator, IO

def iter_pages(fh: IO[bytes]) -> Iterator[str]:
    """
    Stream-parse a Wikipedia multistream XML from a binary file-like object
    (e.g. bz2.open(..., "rb")). Yields each <page> element as a unicode string.
    """
    # Wrap binary stream as text for ElementTree
    text_fh = io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
    # iterparse emits ('end', element) events; check local-name for 'page'
    for event, elem in ET.iterparse(text_fh, events=("end",)):
        if elem.tag.rsplit("}", 1)[-1] == "page":
            yield ET.tostring(elem, encoding="unicode")
            elem.clear()