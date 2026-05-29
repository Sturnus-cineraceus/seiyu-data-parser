import sys

sys.path.insert(0, 'src')

from seiyu_data_parser import media

tests = [
    "TVアニメ",
    "テレビアニメ",
    "アニメーション",
    "アニメ映画",
    "劇場アニメ",
    "劇場版アニメ",
    "映画アニメ",
    "ゲーム",
    "PCゲーム",
    "アプリゲーム",
    "RPG",
    "ノベルゲーム",
    "visual novel",
    "Some animation movie",
    "animation",
    "movie",
    "film",
    "アニメと映画の特別版",
    # OVA cases
    "OVA",
    "OAV",
    "OAD",
    "OV・OVA",
    "全年齢OVA",
    "オリジナルアニメ",
    "オリジナルアニメ (特別)",
    "短編アニメ",
    "パイロットアニメ",
    "短編アニメ 配信",
]

for t in tests:
    try:
        print(f"{t} -> {media._normalize_media_initial(t)}")
    except Exception as e:
        print(f"{t} -> ERROR: {e}")
