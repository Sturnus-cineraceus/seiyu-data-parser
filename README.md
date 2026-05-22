# seiyu-data-parser

Wikipedia の声優関連ページから出演作品情報を抽出して JSON にまとめるツールです。

## 使い方

Wikipedia の multistream `.bz2` ダンプを指定して実行します。

```bash
python seiyu_data_parser.py /path/to/wikipedia-dump.bz2
```

結果は既定で `voice_actor.json` に出力されます。`-o` で出力先を変更できます。

```bash
python seiyu_data_parser.py /path/to/wikipedia-dump.bz2 -o output.json
```

## 主なオプション

- `--limit`: 走査するページ数と出力件数の上限を指定します
- `--exclude-media`: 出力から除外したいメディア名を追加できます

標準でも、いくつかの非対象メディアはあらかじめ除外されます。

## SQLite への取り込み

生成済みの `voice_actor.json` から SQLite ファイルを作れます。

```bash
python seiyu_data_parser_sqlite.py voice_actor.json -o voice_actor.sqlite3
```

作成されるテーブル:

- `voice_actors`
- `works`
- `voice_actor_work_mappings`

マッピングには声優、作品、年が入ります。