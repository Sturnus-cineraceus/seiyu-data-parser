import importlib.util
spec = importlib.util.spec_from_file_location("p", "scripts/parse_text_to_json.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

samples = [
    'title: \"名探偵コナン <!-- 1997-07-14\"',
    'title: \"名探偵コナン <!-- 1997-07-14\"',
    '* [[名探偵コナン (アニメ)|名探偵コナン]]（1997年 - 2021年{{ep|997}}<!-- 2021-02-13 -->、塩田平八郎の妻）<!-- 1997-07-14 -->'
]

for s in samples:
    print("input: ", s)
    print("output:", m.normalize_text(s))
    print()