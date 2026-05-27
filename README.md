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
`voice_actors` には URL 用の `canonical_name_hash` も含まれ、`canonical_name_hash` にユニークインデックスが張られます。
`works` は `wiki_title` を一意キーとして扱い、`title` には表示用の作品名を保持します。

テーブル定義

以下は README に追加する代表的なテーブル定義（SQLite スキーマに基づく）。実装の一次ソースはコード（src/seiyu_data_parser/sqlite_builder.py）です。参考用ドキュメントとして記載しています。

voice_actors

| Column | Type | Nullable | Description | Example |
|---|---:|:---:|---|---|
| id | integer | No | 自動採番される主キー | 1 |
| name | text | No | 声優の表示名（ユニークではない） | "花澤香菜" |
| canonical_name | text | Yes | 正規化されたフルネーム（例: Wikipedia タイトル）。存在することが前提。 | "Hanazawa_Kana" |
| canonical_name_hash | text | Yes | canonical_name の短縮ハッシュ（URL 用、ユニークインデックス） | "XyZ123..." |

works

| Column | Type | Nullable | Description | Example |
|---|---:|:---:|---|---|
| id | integer | No | 自動採番される主キー | 10 |
| media | text | No | メディア種別（例: TV, 映画, ゲーム 等） | "TV" |
| title | text | No | 表示用の作品タイトル | "進撃の巨人" |
| wiki_title | text | No | 作品の Wikipedia タイトル（ユニークキー） | "Shingeki_no_Kyojin" |

voice_actor_work_mappings

| Column | Type | Nullable | Description | Example |
|---|---:|:---:|---|---|
| id | integer | No | 自動採番される主キー | 100 |
| voice_actor_id | integer | No | voice_actors.id への外部キー | 1 |
| work_id | integer | No | works.id への外部キー | 10 |
| year | integer | Yes | クレジットにある年（不明なら NULL） | 2019 |

voice_actor_work_roles

| Column | Type | Nullable | Description | Example |
|---|---:|:---:|---|---|
| id | integer | No | 自動採番される主キー | 1000 |
| mapping_id | integer | No | voice_actor_work_mappings.id への外部キー | 100 |
| role | text | No | 役名（同一 mapping に複数行あり得る） | "エレン・イェーガー" |

注意

- ここに示した定義はコード（sqlite_builder.py）のスキーマと取り込みロジックから抜粋したもので、参考用です。最終的な一次ソースはコードです。
- NULL/Nullable の扱いやユニーク制約は実際の CREATE TABLE 文（コード内）を優先してください。
