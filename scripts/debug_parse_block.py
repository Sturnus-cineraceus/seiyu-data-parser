#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, json
txt = open('data/test.txt', 'r', encoding='utf-8').read()
start = txt.find('{{声優')
if start == -1:
    print('NO BLOCK')
    raise SystemExit(1)
i = start
depth = 0
L = len(txt)
end = -1
while i < L-1:
    if txt[i:i+2] == '{{':
        depth += 1
        i += 2
        continue
    if txt[i:i+2] == '}}':
        depth -= 1
        i += 2
        if depth == 0:
            end = i
            break
        continue
    i += 1
block = txt[start:end] if end != -1 else txt[start:start+4000]
print('---BLOCK SNIPPET---')
print(block[:2000])
fields = {}
for line in block.splitlines():
    m = re.match(r'^\s*\|\s*([^=|]+?)\s*=\s*(.+)$', line)
    if not m:
        continue
    k = m.group(1).strip()
    v = m.group(2).strip()
    v = re.sub(r'\}\}\s*$', '', v).strip()
    fields[k] = v
print('---PARSED FIELDS---')
print(json.dumps(fields, ensure_ascii=False, indent=2))