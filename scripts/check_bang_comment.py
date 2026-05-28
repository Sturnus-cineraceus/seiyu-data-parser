import io, re, json, sys
path = "voice_actor_test2.json"
s = "!--"
try:
    with io.open(path, 'r', encoding='utf-8') as f:
        data = f.read()
except Exception as e:
    print("ERROR: cannot read", path, e)
    sys.exit(2)

count = data.count(s)
print("COUNT:", count)

snips = []
for m in re.finditer(re.escape(s), data):
    if len(snips) >= 20:
        break
    i = m.start()
    start = max(0, i-80)
    end = min(len(data), i+80)
    sn = data[start:end].replace('\\n', '\\\\n')
    snips.append(sn)

for idx, sn in enumerate(snips, 1):
    print(f"--- sample {idx} ---")
    print(sn)