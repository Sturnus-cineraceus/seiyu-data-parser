import sys
from pprint import pprint
sys.path.insert(0, 'src')
from seiyu_data_parser.extract import extract_section, parse_works_section

section_sample = '''== 出演作品 ==
* [[Sample Work]]（役名）

== 次の節 ==
'''

body, level = extract_section(f'<page><text>{section_sample}</text></page>', '出演')
assert 'Sample Work' in body
assert level == 2

section_sample_voice_work = '''== 出演（声優業） ==
* [[Another Work]]（役名）

== 次の節 ==
'''

body2, level2 = extract_section(f'<page><text>{section_sample_voice_work}</text></page>', '出演')
assert 'Another Work' in body2
assert level2 == 2

sample = '''=== 特撮 ===
* [[仮面ライダー剣]]（2004年、ラウザー音声）

=== ナレーション ===
* カウントダウン アカデミー&グラミー木村拓哉的視点（[[WOWOW]]）

=== オーディオブック ===
==== 科学 ====
* 偽善エネルギー 
* [[ロウソクの科学]]（[[竹内敬人]] 邦訳）

==== 数学 ====
* 素数はなぜ人を惹きつけるのか

==== 歴史 ====
* 「24のキーワード」でまるわかり! 最速で身につく世界史
'''

# Simulate that the enclosing '出演' header was level 2 (== 出演 ==),
# so media-level should be level 3 (=== 特撮 === etc.).
pprint(parse_works_section(sample, parent_level=2))
