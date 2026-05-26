"""Centralized media normalization and filtering for seiyu-data-parser.

Expose process_actor(actor: dict) which normalizes media headings, filters out excluded media,
and groups works into [{'media': ..., 'credits': [...]}, ...] to match existing output format.
"""
from typing import Dict, Any, List
import re
import unicodedata

# Exact normalized media strings to exclude (exact normalized match).
EXCLUDE_MEDIA_EXACT = [
    "バラエティ",
    "イベント",
    "ラジオ",
    "その他コンテンツ",
    "CD",
    "担当俳優",
    "CM",
    "レコード、CD",
    "過去",
    "現在",
    "レギュラー",
    "不定期",
    "テレビ番組",
    "特別番組",
    "俳優",
    "女優",
    "担当女優",
    "担当",
    "映画（吹き替え）",
    "吹き替え",
    "テレビドラマ",
    "ドラマ",
    # Note: tokens that should be matched by substring or bounded rules are defined below
]

# Exception tokens: if any of these appear in the normalized media string, the media should NOT be excluded.
# These are higher priority than exclusion tokens (例外トークン ＞ 除外トークン).
EXCEPTION_TOKENS = (
    '声の出演',
    'ナレーション',
    'ボイス',
    '音声',
    'ドラマCD',
    'ドラマＣＤ',
    'オーディオドラマ',
    '声優活動',
    '声優業',
    '声優',
)

# Tokens to match when they appear anywhere in the media string (substring match).
EXCLUDE_MEDIA_CONTAINS = (
    # ① 映像・実写・ビデオ系（partial-match）
    "映画",
    "ドラマ",
    "Vシネマ",
    "ビデオドラマ",
    "ビデオ映画",
    "邦画",
    "時代劇",
    "外画",
    "ビデオ",
    "ビデオシネマ",
    "ビデオムービー",
    "ビデオマガジン",
    "ビデオパッケージ",
    "ビデオグラム",
    "ビデオ / DVD作品",
    "オリジナル・ビデオ",
    "オリジナルビデオ",
    "オリジナルビデオ・DVD",
    "オリジナルDVD",
    "DVD",
    "DVD・BD",
    "DVD・Blu-ray",
    "BD/DVD",
    "BD・DVD",
    "Blu-ray",
    "DVD-ROM",
    "DVDシネマ",
    "IV",
    "VHS",
    "カセット",
    "カセットテープ",
    "ソノシート",

    # ② 配信・Web・ネット・動画系
    "配信",
    "動画",
    "動画配信",
    "ネット",
    "ネット配信",
    "インターネット",
    "インターネット配信",
    "インターネット動画",
    "インターネット動画配信",
    "インターネット放送",
    "インターネット生配信",
    "インターネットTV",
    "ウェブ",
    "web",
    "WEB",
    "Web",
    "YouTube",
    "Youtube",
    "YOUTUBE",
    "ニコニコ動画",
    "ニコニコ生放送",
    "生配信",
    "生放送",
    "オンライン動画",
    "ウェブ配信",
    "Web配信",
    "WEB配信",
    "Web動画",
    "WEB動画",
    "Webムービー",
    "WEBムービー",
    "Webシネマ",
    "WEBシネマ",
    "WebTV",
    "WEBTV",
    "Webコンテンツ",
    "WEBコンテンツ",
    "Webサイト",
    "Webマガジン",
    "WEBマガジン",

    # ③ ドキュメント・教育・資料系
    "ドキュメント",
    "ドキュメンタリー",
    "情報・ドキュメンタリー",
    "ドキュメンタリー・他",
    "教育用ビデオ",
    "教育ビデオ",
    "教育ソフト",
    "教材",
    "教材関連",
    "知育教材",
    "研修ビデオ",
    "インタビュー",
    "インタビュー記事",
    "インタビュー対談",
    "出典",
    "出展",
    "伝記",
    "本",
    "書籍",
    "単行本",
    "ムック本",
    "フォトブック",
    "ブック",
    "著書",
    "著作",
    "月刊ジャイアンツ",
    "カタログ",
    "ストーリーブック",

    # ④ 実写出演・人物系（俳優混入防止）
    "出演",
    "俳優業",
    "女優業",
    "TV出演",
    "外部出演",
    "アナウンサー",
    "アナウンサー時代",
    "フリーアナウンサー",
    "キャスター",
    "レポーター",
    "リポーター",
    "MC",
    "パーソナリティ",
    "パーソナリティ・MC",
    "スタジアムDJ",
    "DJ",
    "VJ",
    "サポーター",
    "サポートミュージシャン",
    "アーティスト活動",
    "SMAP時代",
    "NHK時代",
    "新しい地図時代",

    # ⑤ 舞台・イベント・リアル系
    "演劇",
    "ステージ",
    "ショー",
    "トークショー",
    "トークショウ",
    "ランウェイ",
    "撮影会",
    "ストレートプレイ",
    "コント",
    "即興劇",
    "独演会",
    "演奏会",
    "日本舞踊",
    "ファッションショー",
    "テーマパーク",
    "プラネタリウム",
    "東京ディズニーリゾート",
    "VRアトラクション",
    "アトラクション",
    "プロレス",
    "リングアナウンサー",
    "リングアナ",
    "リング・アナウンサー",
    "グルメリポート",
    "イベント",

    # ⑥ 音楽・制作・作品系ノイズ
    "ボーカル",
    "アルバム",
    "バンド",
    "コーラス",
    "キャラクターソング",
    "LIVE",
    "ライブ",

    "レコーディング",
    "レコーディング参加",
    "作詞作品",
    "作詞提供",
    "ディスコグラフィ",
    "ディスコグラフィー",
    "コンピレーション",
    "コマーシャル",
    "CM",
    "CF",
    "PV",
    "PV・案内",
    "Music Video",
    "MV",
    "MUSIC VIDEO",
    "タイアップ",
    "イメージ作品",
    "イメージビデオ",
    "イメージガール",
    "イメージキャラクター",
    "キャラクター",
    "キャラクターコンテンツ",
    "キャラクター・イメージソング",
    "キャラソン",

    # ⑦ その他ノイズ
    "改名歴",
    "作品",
    "コンテンツ",
    "プロジェクト",
    "その他",
    "そのコンテンツ",
    "そ の他コンテンツ",
    "メディア",
    "メディア企画",
    "メディアミックス",
    "写真集",
    "写真展",
    "イラスト",
    "キャンペーン",
    "コラボ",
    "アンバサダー",
    "タイアップ",
    "ご当地キャラクター",
    "LINEスタンプ",
    "NHK みんなのうた", "NHK くらしの歴史・歴史みつけた", "KaiRan-Van", "CМ", "CV", "CS", "CN", "C M",
    "BS 俳句王国", "AmebaStudio", "ABEMA", "show", "bokura-dansha presents", "うたコン", "WALLOP",
    "VTuber", "V-ライバー活動", "オペラ助演", "インフォマーシャル", "アートワーク", "カラオケ",
    "テレホンサービス", "ソフトウェア", "スチール", "モーションコミック", "モーションキャプチャー",
    "モーションキャプチャ", "モーションアクター", "ポスター", "ボクジェネ", "プロデュース",
    "ビジネスマン必勝講座", "パソコンソフト", "ワンセグ", "再現VTR", "他劇団への客演", "煽りVTR",
    "東京楽笑寄席", "方言指導", "怪談", "執筆活動", "執筆", "国外活動", "館内VTR", "遊技機", "通信系",
    "講演",

    # preserve other original general tokens to avoid regressions
    "テレビ",
    "ラジオ",
    "放送",
    "バラエティ",
    "パチスロ",
    "スロット",
    "パチンコ",
    "舞台",
    "ミュージカル",
    "ミュージック",
    "司会",
    "同人",
    "雑誌",
    "新聞",
    "小説",
    "広告",
    "アパレル",
    "アイドル",
    "アイスショー",
    "モデル",
    "実写",
    "番組",
    "吹替",
    "吹き替え",
    "歌",
    "音楽",
    "ニュース",
    "プロモーション",
    "ユニット",
    "レコード",
    "公演",
    "振付",
    "携帯",
    "脚本",
    "演出",
    "連載",
    "コラム",
    "シングル",
    "スチル",
    "グラビア",
    "VP",
    "公式",
    "受賞",
    "エッセイ",
    "CD",
    "音声CD",
    "音声DVD",
    "ラジオ音声DVD",
    "曲",
    "ダンス",
    "ディレクター",
    "企業",
    "出版",
    "映像",
    "本人",
    "玩具",
    "落語",
    "芝居",
    "講師",
    "語り",
    "自主",
    "公演",
    "肖像",
    "顔出し",
    "特番",
    "狂言",
    "大使",
    "製品",
    "主催",
    "コンサート",
    "実況",
    "学校",
    "広報"
)

def _normalize_media_initial(s: str) -> str:
    if not isinstance(s, str):
        return ""
    m = s
    # normalize full/halfwidth differences etc.
    m = unicodedata.normalize('NFKC', m)
    m = re.sub(r'<.*?>', '', m)
    m = re.sub(r'\{\{.*?\}\}', '', m, flags=re.S)
    m = m.replace('、', ',').replace('　', ' ').strip()
    # normalize fullwidth CD to ASCII for matching
    m = m.replace('ＣＤ', 'CD')
 
    # Map certain tokens explicitly into the canonical 'その他' group per mapping rules.
    # These are specific non-media tokens that should be grouped into 'その他' rather than excluded.
    other_tokens = [
        '声優活動', '声優業', '声優口演', '声優', '声の出演',
        '音声データ', '音声コミック', '音声DVD', '音声CD',
        'グッズ音声', 'キャラクターボイス', 'アフレコ', '着ボイス',
        '玩具音声', 'プラネタリウムの声の出演'
    ]
    # Treat an exact single-token '他' as その他 as well
    if m.strip() == '他' or any(tok in m for tok in other_tokens):
        return 'その他'
 
    # Map TV anime variants to canonical 'アニメ' early so subsequent 'テレビ' exclusion
    # does not remove TV anime entries. Handle common variants like 'TVアニメ',
    # 'テレビアニメ', and their variants with common separators (・, /, -, etc.).
    if re.search(r'(?:TV|ＴＶ|テレビ)[\s・\-/／―]*アニメ(?:ーション)?', m):
        return 'アニメ'

    # Map various audio-related variants to a single canonical media 'オーディオドラマ'.
    # Match common prefixes and tokens but avoid mapping lone 'CD' or generic 'ラジオ'.
    audio_tokens = [
        # 既存
        'オーディオドラマ', 'オーディオブック', 'オーディドラマ', 'オーディブック', 'オーディ',
        'ボイスドラマ', 'ボイスブック', 'ボイスCD', 'ボイスＣＤ',
        'カセットドラマ', 'カセットブック', 'カセット文庫', '朗読',
        'ドラマCD', 'ドラマＣＤ', 'ラジオドラマ','音声ドラマ', 'ラジオCD', 'ラジオＣＤ','イヤードラマ','CDドラマ',
 
        # 追加（強い）
        'サウンドドラマ', '音声作品', '音声コンテンツ', 'ボイスシアター', '声劇',
 
        # 追加（コミック系・類縁）
        'ムービーコミック', 'コミックムービー', 'デジタルコミック・ボイスコミック', 'デジタルコミック',
        'ボイスコミックス', 'ボイスコミック', 'ボイスコミック(発表年以降も複数話制作あり)',
        'アテレコ', '+Voice', '＋Voice',
 
        # 追加（現代系）
        'ASMR', 'ASMR音声作品', 'ASMRコンテンツ', 'ポッドキャスト',
 
        # 条件付き（必要なら）
        '音声配信'
    ]
    if any(tok in m for tok in audio_tokens):
        return 'オーディオドラマ'

    # New mapping: prioritize anime vs theatrical anime, then games.
    # Check both Japanese tokens and lowercase English tokens.
    m_lower = m.lower()
    anime_tokens = ['アニメ', 'animation', 'anime']
    movie_tokens = ['映画', '劇場', '劇場版', 'movie', 'film']
    tv_stream_tokens = ['tv', 'ＴＶ', 'テレビ', '配信', 'web', 'ネット', 'stream', '配信アニメ', 'ネット配信']
    game_tokens = ['ゲーム', 'game', 'app', 'アプリ', 'pc', 'コンシューマ', 'コンシューマー', 'rpg', 'ノベル', 'visual novel', 'adv', 'ps4']

    has_anime = any((tok in m) or (tok in m_lower) for tok in anime_tokens)
    has_movie = any((tok in m) or (tok in m_lower) for tok in movie_tokens)
    has_game = any((tok in m) or (tok in m_lower) for tok in game_tokens)

    # 劇場アニメ優先：アニメ要素かつ映画/劇場要素がある場合
    if has_anime and has_movie:
        return '劇場アニメ'
    # TV / 配信 のアニメを優先（例: 配信アニメ）
    has_tv_stream = any((tok in m) or (tok in m_lower) for tok in tv_stream_tokens)
    if has_anime and has_tv_stream:
        return 'アニメ'

    # OVA 判定（優先度は 劇場アニメ > TV/配信アニメ > OVA ）
    # 無条件トークン（OVA系）
    # Match OVA-like ASCII tokens but avoid matching substrings inside English words (e.g., 'novel').
    # Use negative lookbehind/lookahead for ASCII alphanumerics.
    if re.search(r'(?i)(?<![A-Za-z0-9])(?:ova|oav|oad|ov)(?![A-Za-z0-9])', m):
        # ただし映画・劇場・TV・配信・ドラマ等が含まれる場合は OVA にしない
        if not has_movie and not has_tv_stream and 'ドラマ' not in m:
            return 'OVA'

    # 「オリジナルアニメ」を含み、かつ TV/映画/劇場 を含まない場合は OVA
    if 'オリジナルアニメ' in m and not (has_movie or has_tv_stream):
        return 'OVA'

    # 「短編アニメ」または「パイロットアニメ」を含み、かつTV/映画/配信/Web/ネットを含まない場合はOVA
    if (('短編アニメ' in m) or ('パイロットアニメ' in m)) and not (has_movie or has_tv_stream or '配信' in m or 'web' in m.lower() or 'ネット' in m):
        return 'OVA'

    # テレビ等のアニメ（映画要素を含まない）
    if has_anime and not has_movie:
        return 'アニメ'
    # ゲーム要素があればゲームにまとめる
    if has_game:
        return 'ゲーム'

    if '特撮' in m or '特攝' in m:
        return '特撮'
    if 'CM' in m or 'ＣＭ' in m:
        return 'CM'
    m = m.replace('バラエティー', 'バラエティ')
    if 'バラエティ' in m:
        return 'バラエティ'

    # Narration detection: match listed tokens (substring match) but exclude when
    # certain audio/drama tokens are present (e.g., ドラマ, CD, ASMR).
    NARRATION_TOKENS = (
        'ナレーション', 'アナウンス', 'ヴォイスオーバー', 'ボイスオーバー', 'ボイオーバー',
        '音声案内', '音声ガイド', '音声解説', '副音声（音声ガイド）', '音声提供',
        '館内アナウンス', '館内放送', '店内放送', '車内放送', '車内放送・ホーム案内', '車内アナウンス',
        '駅構内放送', '駅構内アナウンス', '駅自動放送', '自動放送・音声案内', '自動放送アナウンス',
        '機内放送', 'バス車内案内', '電話案内', '有線放送', '施設アナウンス等',
        '公園・娯楽施設・館内アナウンス', '博物館子供用音声ガイド', 'ラジオ音声DVD', 'ナレーター'
    )
    # If any of these appear, treat as narration unless an exclusion token is present.
    NARRATION_EXCLUDE_TOKENS = ('ドラマ', 'CD', 'ボイスドラマ', 'サウンドドラマ', 'オーディオ', 'ASMR')
    if any(tok in m for tok in NARRATION_TOKENS):
        if not any(ex in m for ex in NARRATION_EXCLUDE_TOKENS):
            return 'ナレーション'

    if 'イベント' in m:
        return 'イベント'
    m = m.replace('パチスロー', 'パチスロ')
    m = m.replace('パチンコー', 'パチンコ')
    if 'パチスロ' in m or 'スロット' in m:
        return 'パチスロ'
    if 'パチンコ' in m:
        return 'パチンコ'
    if 'ゲーム' in m:
        return 'ゲーム'
    return m

def _normalize_media_final(s: str) -> str:
    if not isinstance(s, str):
        return ""
    m = s
    # Final normalization: canonicalize any media containing 'その他' to 'その他'
    if 'その他' in m:
        return 'その他'
    return m

# Derived exclusion helpers built from the canonical constant groups above.
# Exact normalized set for quick equality checks (use initial normalization here).
EXCLUDE_MEDIA_SET = frozenset(_normalize_media_initial(m) for m in EXCLUDE_MEDIA_EXACT)

# All tokens treated as substring (任意位置部分一致) for exclusion.
EXCLUDE_CONTAINS = tuple(EXCLUDE_MEDIA_CONTAINS)

# short ASCII tokens handled with word-boundary regex to avoid substring false positives
EXCLUDE_ASCII_RE = re.compile(r'\b(?:bd|dvd|vhs|iv|cm|pv|mv|youtube|web|tv|net|cv|cs|cn|bs|abema|vtuber)\b', re.I)


def process_actor(actor: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize, filter and group works for a single actor record.

    Input actor: {"name": ..., "wiki_title": ..., "works": [ {"media": raw, "title":..., ...}, ... ]}
    Output actor has works grouped as [{"media": normalized_media, "credits": [...]}, ...].
    """
    if not isinstance(actor, dict):
        return actor
    works = actor.get("works")
    if not isinstance(works, list):
        return actor

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for w in works:
        if not isinstance(w, dict):
            continue
        media_raw = w.get("media")
        nm_initial = _normalize_media_initial(media_raw) if isinstance(media_raw, str) else ""
        # Prepare a minimal cleaned version of the original media string (before aggressive mappings)
        raw_clean = ""
        if isinstance(media_raw, str):
            raw_clean = re.sub(r'<.*?>', '', media_raw)
            raw_clean = re.sub(r'\{\{.*?\}\}', '', raw_clean, flags=re.S)
            raw_clean = raw_clean.replace('、', ',').replace('　', ' ').strip()
            raw_clean = raw_clean.replace('ＣＤ', 'CD')
        nm_initial_lower = nm_initial.lower()
        raw_clean_lower = raw_clean.lower()

        # Exception tokens have highest priority: check normalized value only.
        if nm_initial and any(tok.lower() in nm_initial_lower for tok in EXCEPTION_TOKENS):
            # keep this media (do not exclude)
            pass
        else:
            # If nm_initial is empty, allow exception if raw_clean contains an exception token.
            if not nm_initial:
                if any(tok.lower() in raw_clean_lower for tok in EXCEPTION_TOKENS):
                    # raw indicates voice-related content; do not exclude
                    pass
                else:
                    # cannot safely match; do not exclude by default
                    pass
            else:
                # If normalization mapped to 'その他' but raw text contains an exception token,
                # treat it as exception (do not exclude) so voice entries survive.
                if nm_initial == 'その他' and any(tok.lower() in raw_clean_lower for tok in EXCEPTION_TOKENS):
                    pass
                else:
                    # Exact normalized exclusion (first)
                    if nm_initial in EXCLUDE_MEDIA_SET:
                        continue
                    # Substring exclusion against normalized value only (case-insensitive)
                    # also check short ASCII tokens with word-boundary regex to avoid false positives
                    if EXCLUDE_ASCII_RE.search(nm_initial_lower) or any(tok.lower() in nm_initial_lower for tok in EXCLUDE_CONTAINS):
                        continue
        # Final normalization (e.g., map 'その他' to canonical 'その他')
        nm_final = _normalize_media_final(nm_initial) or (media_raw or "Unknown")
        media_key = nm_final
        entry = {k: v for k, v in w.items() if k != "media"}
        grouped.setdefault(media_key, []).append(entry)

    actor["works"] = [{"media": m, "credits": c} for m, c in grouped.items()]
    return actor