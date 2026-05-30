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
        'name': 'parenthesized role with trailing annotation suffix keeps canonical title',
        'mode': 'works_section',
        'section_text': '=== アニメ ===\n* この空の下で（2020年、[[田熊常吉]]） - [[タクマ (企業)|タクマ]]企業アニメーション<!-- 2020-10-19 -->\n',
        'expected_title': 'この空の下で',
        'expected_roles': ['田熊常吉'],
        'expected_year': 2020,
        'expected_canonical': 'この空の下で',
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
        'name': 'tokusatsu episode and broadcaster suffix is excluded from title',
        'line': '激走戦隊カーレンジャー 第21話（1996年7月19日、テレビ朝日） - AAアバンバ（声） 役',
        'expected_title': '激走戦隊カーレンジャー',
        'expected_roles': ['AAアバンバ'],
    },
    {
        'name': 'no year heading picks year from date and broadcaster parentheses',
        'mode': 'works_section',
        'section_text': '=== 特撮 ===\n* [[激走戦隊カーレンジャー]] 第21話（1996年7月19日、テレビ朝日） - AAアバンバ（声） 役\n',
        'expected_title': '激走戦隊カーレンジャー',
        'expected_roles': ['AAアバンバ'],
        'expected_year': 1996,
    },
    {
        'name': 'no year heading picks year from year and broadcaster parentheses',
        'mode': 'works_section',
        'section_text': '=== 特撮 ===\n* [[激走戦隊カーレンジャー]] 第21話（1996年、テレビ朝日） - AAアバンバ（声） 役\n',
        'expected_title': '激走戦隊カーレンジャー',
        'expected_roles': ['AAアバンバ'],
        'expected_year': 1996,
    },
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
    {
        'name': 'inline parenthesized year populates year and is removed from title',
        'mode': 'works_section',
        'section_text': '=== アニメ ===\n* [[デビルマンレディー]]（1998年） - 女性ライター、レミの母\n',
        'expected_title': 'デビルマンレディー',
        'expected_roles': ['女性ライター', 'レミの母'],
        'expected_year': 1998,
    },
    {
        'name': 'year range in parentheses with outside roles uses earliest year',
        'mode': 'works_section',
        'section_text': '=== テレビアニメ ===\n* [[名探偵コナン (アニメ)|名探偵コナン]]（1998年 - 1999年{{ep|129}}<!-- 1999-01-04 -->） - 岡崎澄江{{ep|118}}、俊也の母{{ep|129}}<!-- 1998-09-21 -->\n',
        'expected_title': '名探偵コナン',
        'expected_roles': ['岡崎澄江', '俊也の母'],
        'expected_year': 1998,
    },
    {
        'name': 'inline year and role in same parentheses without year heading',
        'mode': 'works_section',
        'section_text': '=== テレビアニメ ===\n* [[風の中の少女 金髪のジェニー]]（1992年、ローザ）\n',
        'expected_title': '風の中の少女 金髪のジェニー',
        'expected_roles': ['ローザ'],
        'expected_year': 1992,
    },
    {
        'name': 'pop team epic year range and in-parenthesis role with broadcast note',
        'mode': 'works_section',
        'section_text': "=== テレビアニメ ===\n* [[ポプテピピック]]（2018年 - 2021年、'''ポプ子'''〈第8話Bパート / 再放送・リミックス版第6話Bパート〉<ref>{{Cite web|和書|work=TVアニメ「ポプテピピック」公式サイト|title=キャスト|url=http://hoshiiro.jp/cast/|accessdate=2019-05-02}}</ref>）<!-- 2018-02-25 -->\n",
        'expected_title': 'ポプテピピック',
        'expected_roles': ['ポプ子'],
        'expected_year': 2018,
    },
    {
        'name': 'monogatari year range and role in parentheses with series suffix note',
        'mode': 'works_section',
        'section_text': "=== テレビアニメ ===\n* [[物語シリーズ]]（2012年 - 2014年{{ep|2|s=花物語}}<!-- 2014-08-16 -->、'''貝木泥舟'''{{ep|3|s=偽物語}}） - シリーズ{{Ras|『[[偽物語]]』（2012年）<!-- 2012-01-21 #3 -->、『[[〈物語〉シリーズ セカンドシーズン]]』（2013年）<!-- 2013-11-23 #21 -->、『[[花物語 (西尾維新)|花物語]]』（2014年）<!-- 2014-08-16 #2 -->}}\n",
        'expected_title': '物語シリーズ',
        'expected_roles': ['貝木泥舟'],
        'expected_year': 2012,
    },
    {
        'name': 'corpse party ova aggregate note does not become role',
        'mode': 'works_section',
        'section_text': "=== OVA ===\n| 2012年 |\n* [[コープスパーティー#OVA|コープスパーティー OVAシリーズ]]（2012年 - 2013年、'''篠崎あゆみ'''<ref>{{Cite web|和書|publisher=コープスパーティー Tortured Souls -暴虐された魂の呪叫-|url=https://corpse.jp/?cont=5|title=キャラクター|accessdate=2013-03-02}}</ref>）- 1作品(OAD)+1シリーズ(ODS上映)\n",
        'expected_title': 'コープスパーティー OVAシリーズ',
        'expected_roles': ['篠崎あゆみ'],
        'expected_year': 2012,
    },
]


def _assert_case(case):
    mode = case.get('mode', 'item_line')
    if mode == 'works_section':
        parsed = parse_works_section(case['section_text'], parent_level=case.get('parent_level', 2))
        assert parsed, f"[{case['name']}] no parsed result"
        title = parsed[0].get('title', '')
        roles = parsed[0].get('roles', [])
        year = parsed[0].get('year', '')
        canonical_name = parsed[0].get('canonical_name', '')
        input_text = case['section_text']
    else:
        title, roles = _parse_item_line(case['line'])
        year = None
        canonical_name = None
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

    if 'expected_year' in case:
        assert year == case['expected_year'], (
            f"[{case['name']}] year mismatch\n"
            f"  input   : {input_text}\n"
            f"  expected: {case['expected_year']}\n"
            f"  actual  : {year}"
        )

    if 'expected_canonical' in case:
        assert canonical_name == case['expected_canonical'], (
            f"[{case['name']}] canonical_name mismatch\n"
            f"  input   : {input_text}\n"
            f"  expected: {case['expected_canonical']}\n"
            f"  actual  : {canonical_name}"
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
