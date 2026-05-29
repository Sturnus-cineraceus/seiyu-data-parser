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
- `voice_actor_work_roles`
- `voice_actors_ngrams_fts` (FTS5)

`voice_actors` には検索用に name_ngrams（バイグラム）列と canonical_name_hash（URL 用の短縮ハッシュ）を含み、`birth_date` / `death_date` / `gender` も格納されます。`canonical_name` と `canonical_name_hash` にユニークインデックスが張られます。
`works` は内部的には `canonical_name` を作品の一意識別子として扱い、`canonical_name_hash` を保持します。表示用の作品名は `title` に格納します。


テーブル定義

以下は README に追加する代表的なテーブル定義（SQLite スキーマに基づく）。実装の一次ソースはコード（src/seiyu_data_parser/sqlite_builder.py）です。参考用ドキュメントとして記載しています。

voice_actors

| Column | Type | Nullable | Description | Example |
|---|---:|:---:|---|---|
| id | integer | No | 自動採番される主キー | 1 |
| name | text | No | 声優の表示名（ユニークではない） | "花澤香菜" |
| name_ngrams | text | Yes | 名前から生成したバイグラム（スペース区切り）。FTS インデックス用。例: "あい いう" | "あい いう" |
| canonical_name | text | Yes | 正規化されたフルネーム（既に存在する場合は一意） | "Hanazawa_Kana" |
| canonical_name_hash | text | Yes | canonical_name の短縮ハッシュ（URL 用、ユニークインデックス） | "XyZ123..." |
| furigana | text | Yes | ふりがな（読み仮名） | "はなざわ かな" |
| furigana_ngrams | text | Yes | ふりがなから生成したバイグラム（スペース区切り） | "はな なさ さわ" |
| agency | text | Yes | 所属事務所名 | "大沢事務所" |
| agency_ngrams | text | Yes | 事務所名から生成したバイグラム（スペース区切り） | "大沢 沢事 事務 務所" |
| official_site | text | Yes | 公式サイト URL | "https://example.com" |
| birth_date | date | Yes | 生年月日（YYYY-MM-DD） | "1989-02-25" |
| death_date | date | Yes | 没年月日（YYYY-MM-DD） | "2012-04-09" |
| gender | text | Yes | カテゴリから推定した性別（例: male/female） | "female" |

-- 付記: `canonical_name` と `canonical_name_hash` にはそれぞれユニークインデックスが作られます（NULL は許容されます）。

works

| Column | Type | Nullable | Description | Example |
|---|---:|:---:|---|---|
| id | integer | No | 自動採番される主キー | 10 |
| media | text | No | メディア種別（例: TV, 映画, ゲーム 等） | "TV" |
| title | text | No | 表示用の作品タイトル | "進撃の巨人" |
| canonical_name | text | No | 作品の一意識別子。内部的に主要なキーとして扱う（UNIQUE）。 | "Shingeki_no_Kyojin" |
| canonical_name_hash | text | Yes | canonical_name の短縮ハッシュ（URL 用、ユニークインデックス） | "AbC456..." |

voice_actor_work_mappings

| Column | Type | Nullable | Description | Example |
|---|---:|:---:|---|---|
| id | integer | No | 自動採番される主キー | 100 |
| voice_actor_id | integer | No | voice_actors.id への外部キー | 1 |
| work_id | integer | No | works.id への外部キー | 10 |
| year | integer | Yes | クレジットにある年（不明なら NULL） | 2019 |

-- 付記: (voice_actor_id, work_id, COALESCE(year, -1)) に対するユニークインデックスがあり、年が不明な場合の重複を扱います。

voice_actor_work_roles

| Column | Type | Nullable | Description | Example |
|---|---:|:---:|---|---|
| id | integer | No | 自動採番される主キー | 1000 |
| mapping_id | integer | No | voice_actor_work_mappings.id への外部キー | 100 |
| role | text | No | 役名（同一 mapping に複数行あり得る） | "エレン・イェーガー" |

-- 付記: mapping_id と role の組にユニークインデックスがあります。

FTS / 検索補助テーブル

- `voice_actors_ngrams_fts` (FTS5, external content): name_ngrams をインデックス化するための仮想テーブルです。voice_actors の rowid を content_rowid としてバインドし、INSERT/UPDATE/DELETE 用のトリガで同期されます。


注意

- ここに示した定義はコード（sqlite_builder.py）のスキーマと取り込みロジックから抜粋したもので、参考用です。最終的な一次ソースはコードです。
- NULL/Nullable の扱いやユニーク制約は実際の CREATE TABLE 文（コード内）を優先してください。
