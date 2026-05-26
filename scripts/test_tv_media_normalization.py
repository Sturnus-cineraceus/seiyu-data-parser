import sys
sys.path.insert(0, "src")
from seiyu_data_parser import media as media_mod

tests = [
    "テレビアニメ",
    "テレビ・アニメ",
    "TV／アニメ",
    "テレビ番組",
    "TV-アニメ",
    "ＴＶアニメ",
    "TVアニメーション",
]

for t in tests:
    actor = {"name": "Test", "works": [{"media": t, "title": "Sample", "wiki_title": "Sample", "roles": []}]}
    out = media_mod.process_actor(actor.copy())
    print("INPUT:", repr(t))
    print("NM_INITIAL:", media_mod._normalize_media_initial(t))
    print("OUTPUT_WORKS:", out.get("works"))
    print("-" * 40)