import sys, json
sys.path.insert(0, 'src')
from seiyu_data_parser.extract import extract_section, parse_works_section

with open('data/test.txt', 'r', encoding='utf-8') as f:
    s = f.read()

page_xml = f"<page><text><![CDATA[{s}]]></text></page>"
body, level = extract_section(page_xml, '出演')
print('PARENT_LEVEL:', level)
res = parse_works_section(body, parent_level=level)
print(json.dumps(res, ensure_ascii=False, indent=2))