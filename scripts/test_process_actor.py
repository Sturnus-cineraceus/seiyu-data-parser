import sys, json
sys.path.insert(0, 'src')
from seiyu_data_parser.extract import extract_section, parse_works_section
from seiyu_data_parser.media import process_actor

with open('data/test.txt', 'r', encoding='utf-8') as f:
    s = f.read()

page_xml = f"<page><text><![CDATA[{s}]]></text></page>"
body, level = extract_section(page_xml, '出演')
works = parse_works_section(body, parent_level=level)

actor = {"name": "片桐仁", "wiki_title": "片桐仁", "works": works}
processed = process_actor(actor)
print(json.dumps(processed, ensure_ascii=False, indent=2))