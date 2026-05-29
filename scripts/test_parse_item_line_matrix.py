import argparse
import sys

sys.path.insert(0, 'src')

from seiyu_data_parser.extract import _parse_item_line
from seiyu_data_parser.extract import parse_works_section


# Stable regression cases: these should pass now and continue to pass.
STABLE_CASES = [
    {
        'name': 'simple parenthesized role',
        'line': '名探偵コナン（1997年 - 2021年、塩田平八郎の妻）',
        'expected_title': '名探偵コナン',
        'expected_roles': ['塩田平八郎の妻'],
    },
    {
        'name': 'multiple roles in parentheses',
        'line': '週刊ストーリーランド（1999年 - 2000年、山田まり子、太った女、ピエール）',
        'expected_title': '週刊ストーリーランド',
        'expected_roles': ['山田まり子', '太った女', 'ピエール'],
    },
    {
        'name': 'nested parentheses in role',
        'line': 'クッキングパパ（吉岡（荒岩）カツ代）',
        'expected_title': 'クッキングパパ',
        'expected_roles': ['吉岡カツ代'],
    },
    {
        'name': 'fallback hyphen role without role marker',
        'line': 'ルパン三世 GREEN vs RED - ヤスオ',
        'expected_title': 'ルパン三世 GREEN vs RED',
        'expected_roles': ['ヤスオ'],
    },
    {
        'name': 'explicit role marker and starring prefix removal',
        'line': '世にも奇妙な物語 秋の特別編（2008年9月23日） - 主演・篠塚香織 役',
        'expected_title': '世にも奇妙な物語 秋の特別編（2008年9月23日）',
        'expected_roles': ['篠塚香織'],
    },
    {
        'name': 'numeric role is retained',
        'line': '作品名（2001年、009）',
        'expected_title': '作品名',
        'expected_roles': ['009'],
    },
]


# Target bug-fix cases: enable after implementing suffix trimming logic.
TARGET_CASES = [
    {
        'name': 'external link label is parsed as title',
        'mode': 'works_section',
        'section_text': '=== ゲーム ===\n* [https://www.over-eclipse.com/ オーバーエクリプス]（ポラリス）\n',
        'expected_title': 'オーバーエクリプス',
        'expected_roles': ['ポラリス'],
    },
    {
        'name': 'aggregate suffix with series and specials',
        'line': 'ONE PIECE（1999年 - 、シャンクス） - 1シリーズ + 特別編2作品',
        'expected_title': 'ONE PIECE',
        'expected_roles': ['シャンクス'],
    },
    {
        'name': 'aggregate suffix with trilogy count',
        'line': '機動戦士ガンダム I - III（1981年 - 1982年、シャア） - 3部作',
        'expected_title': '機動戦士ガンダム I - III',
        'expected_roles': ['シャア'],
    },
    {
        'name': 'aggregate suffix with multi-series count',
        'line': 'ヴァンドレッド（2000年 - 2001年、ウータン） - 2シリーズ',
        'expected_title': 'ヴァンドレッド',
        'expected_roles': ['ウータン'],
    },
    {
        'name': 'non-role suffix with bd dvd note',
        'line': 'C3 -シーキューブ-（世界橋ガブリエル） - BD/DVD第5巻TV未放送話',
        'expected_title': 'C3 -シーキューブ-',
        'expected_roles': ['世界橋ガブリエル'],
    },
    {
        'name': 'non-role suffix with rebroadcast note',
        'line': '機動戦士ガンダム THE ORIGIN（2015年 - 2018年、シャア・アズナブル〈キャスバル・レム・ダイクン〉 / エドワウ・マス） - 2019年に再編集作品『THE ORIGIN 前夜 赤い彗星』テレビ放送',
        'expected_title': '機動戦士ガンダム THE ORIGIN',
        'expected_roles': ['シャア・アズナブル', 'エドワウ・マス'],
    },
    {
        'name': 'ova line with no-space hyphen suffix keeps role',
        'line': 'To LOVEる -とらぶる- OVA（2009年 - 2010年、古手川唯）- コミックス第13巻 - 第18巻限定版',
        'expected_title': 'To LOVEる -とらぶる- OVA',
        'expected_roles': ['古手川唯'],
    },
    {
        'name': 'single wikilink label parentheses are not roles',
        'mode': 'works_section',
        'section_text': '=== アニメ ===\n* [[ゲゲゲの鬼太郎 (テレビアニメ第2シリーズ)|ゲゲゲの鬼太郎（第2作）]]\n',
        'expected_title': 'ゲゲゲの鬼太郎',
        'expected_roles': [],
    },
    {
        'name': 'haikyu aggregate and theatrical note keeps cast role',
        'mode': 'works_section',
        'section_text': "=== テレビアニメ ===\n* [[ハイキュー!!]]（2014年 - 2020年、'''清水潔子'''<ref>{{Cite web|和書|work=アニメ『ハイキュー!!』|title=STAFF&CAST|url=http://www.j-haikyu.com/anime/staff.html|accessdate=2019-09-22|archiveurl=https://web.archive.org/web/20141224050312/http://www.j-haikyu.com/anime/staff.html|archivedate=2014-12-24}}</ref><ref>{{Cite web|和書|work=アニメ『ハイキュー!! 烏野高校 VS 白鳥沢学園高校』|title=STAFF&CAST スタッフ&キャスト|url=http://www.j-haikyu.com/anime/staff.html|accessdate=2019-09-22}}</ref><ref>{{Cite web|和書|url=https://haikyu.jp/staffcast/|title=STAFF & CAST|work=アニメ『ハイキュー!!』公式サイト|accessdate=2019-09-22}}</ref>） - 5シリーズ{{Ras|第1期（2014年）、第2期『セカンドシーズン』（2015年 - 2016年）、第3期『烏野高校 VS 白鳥沢学園高校』（2016年）、第4期『TO THE TOP』第1クール（2020年）、第4期『TO THE TOP』第2クール（2020年）}} / 2015年に総集編『終わりと始まり』劇場上映\n",
        'expected_title': 'ハイキュー!!',
        'expected_roles': ['清水潔子'],
    },
]


def _assert_case(case):
    mode = case.get('mode', 'item_line')
    if mode == 'works_section':
        parsed = parse_works_section(case['section_text'], parent_level=case.get('parent_level', 2))
        assert parsed, f"[{case['name']}] no parsed result"
        title = parsed[0].get('title', '')
        roles = parsed[0].get('roles', [])
        input_text = case['section_text']
    else:
        title, roles = _parse_item_line(case['line'])
        input_text = case['line']

    assert title == case['expected_title'], (
        f"[{case['name']}] title mismatch\n"
        f"  input   : {input_text}\n"
        f"  expected: {case['expected_title']}\n"
        f"  actual  : {title}"
    )
    assert roles == case['expected_roles'], (
        f"[{case['name']}] roles mismatch\n"
        f"  input   : {input_text}\n"
        f"  expected: {case['expected_roles']}\n"
        f"  actual  : {roles}"
    )


def run(cases, label):
    failed = 0
    print(f'Running {label}: {len(cases)} cases')
    for case in cases:
        try:
            _assert_case(case)
            print(f"  OK  - {case['name']}")
        except AssertionError as e:
            failed += 1
            print(f"  NG  - {case['name']}")
            print(str(e))
    return failed


def main():
    parser = argparse.ArgumentParser(
        description='Regression matrix for _parse_item_line.'
    )
    parser.add_argument(
        '--include-target',
        action='store_true',
        help='Also run target bug-fix cases (expected to fail before fix).',
    )
    args = parser.parse_args()

    failed = 0
    failed += run(STABLE_CASES, 'stable cases')

    if args.include_target:
        failed += run(TARGET_CASES, 'target bug-fix cases')
    else:
        print('Skipping target bug-fix cases. Use --include-target to run them.')

    if failed:
        print(f'\nFAILED: {failed} case(s)')
        raise SystemExit(1)

    print('\nPASSED: all selected cases')


if __name__ == '__main__':
    main()
