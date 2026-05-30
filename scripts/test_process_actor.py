import json
import os
import sys

sys.path.insert(0, 'src')
from seiyu_data_parser.extract import extract_section, parse_works_section
from seiyu_data_parser.media import process_actor

fixture_path = os.path.join('data', 'test.txt')
if os.path.exists(fixture_path):
    with open(fixture_path, 'r', encoding='utf-8') as f:
        s = f.read()
else:
    s = '''
== 出演 ==
=== テレビアニメ ===
* [[To LOVEる -とらぶる- OVA]]（2009年 - 2010年、古手川唯）- コミックス第13巻 - 第18巻限定版
'''

page_xml = f"<page><text><![CDATA[{s}]]></text></page>"
body, level = extract_section(page_xml, '出演')
works = parse_works_section(body, parent_level=level)

actor = {"name": "片桐仁", "wiki_title": "片桐仁", "works": works}
processed = process_actor(actor)
print(json.dumps(processed, ensure_ascii=False, indent=2))


def test_exclude_sound_production_media() -> None:
    actor = {
        "name": "Test",
        "wiki_title": "Test",
        "works": [
            {"media": "音響制作", "title": "取り込まれない作品"},
            {"media": "テレビアニメ", "title": "取り込まれる作品"},
        ],
    }
    out = process_actor(actor)
    medias = [w.get("media") for w in out.get("works", [])]
    assert "音響制作" not in medias, f"音響制作 が除外されていません: {medias}"
    assert "アニメ" in medias, f"テレビアニメ が正規化されていません: {medias}"
    print("OK: 音響制作 media is excluded")


if __name__ == '__main__':
    test_exclude_sound_production_media()