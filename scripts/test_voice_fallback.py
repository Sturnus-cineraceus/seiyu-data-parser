import sys
from pprint import pprint
sys.path.insert(0, 'src')
from seiyu_data_parser.extract import extract_section, parse_works_section, _parse_item_line

def test_voice_fallback():
    with open('data/test.txt', 'r', encoding='utf-8') as f:
        s = f.read()
    page_xml = f"<page><text><![CDATA[{s}]]></text></page>"
    body, level = extract_section(page_xml, '出演')
    res = parse_works_section(body, parent_level=level)
    # find OVA entry
    ova = [r for r in res if 'ルパン三世 GREEN vs RED' in r['title']]
    assert ova, 'OVA entry not found'
    assert any('ヤスオ' in role for r in ova for role in r['roles']), '役名ヤスオが抽出されていません'
    print('OK: fallback roles extracted')


def test_nested_parentheses_role_normalization():
    title, roles = _parse_item_line('クッキングパパ（吉岡（荒岩）カツ代）')
    assert title == 'クッキングパパ', f'タイトル抽出失敗: {title}'
    assert roles == ['吉岡カツ代'], f'役名抽出失敗: {roles}'
    print('OK: nested parentheses role normalized')

if __name__ == '__main__':
    test_voice_fallback()
    test_nested_parentheses_role_normalization()