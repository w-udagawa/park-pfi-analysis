# CLAUDE.md — Park-PFI Analysis

## プロジェクト概要

都市公園の Park-PFI（公募設置管理制度）導入ポテンシャルを **「にぎわい創出」単一軸** で定量化する Streamlit Web アプリ + Python 分析ツール。東京都・神奈川県・埼玉県・千葉県の任意の市区町村に対応。

**メイン軸**: にぎわいスコア (0〜100 の連続値) = 流量%ile × 0.6 + 商業スコア × 0.4
**サブ評価**: 老朽 / 子育て / 地域拠点 / 防災 の 4 バッジ（●/空白）

## アーキテクチャ

```
app.py                            # Streamlit エントリポイント (Web UI)
main.py                           # run_pipeline() + CLI エントリ
  ├── src/config_loader.py        # YAML 読み込み + API キー解決 (st.secrets / env / .env)
  ├── src/webapp.py               # Web 用ヘルパー (自治体選択・bbox 計算・config 構築)
  ├── src/data_collector.py       # GeoJSON + MLIT DPF + Overpass API データ収集 (cache 付き)
  ├── src/data_validator.py       # データ品質診断
  ├── src/pedestrian_flow.py      # 半径700m圏の駅乗降客数を単純合計 + パーセンタイル正規化
  ├── src/surrounding_analysis.py # 周辺施設 6 カテゴリ分析 (半径 500m)
  ├── src/vibrancy_evaluator.py   # にぎわいスコア計算 + 4 バッジ判定
  └── src/report_generator.py     # Excel (9 シート) + Markdown レポート
```

**旧アーキテクチャからの変更点**:
- `src/pfi_classifier.py` + `src/scoring.py` は廃止
- 5 類型分類 + 5 軸複合スコアを、**にぎわいスコア 1 軸 + 4 バッジ** に置き換え
- Excel は 11 シート → 9 シートに再構成

## 実行方法

### Web アプリ (推奨)

```bash
cd /mnt/c/ClaudeWork/park-pfi-analysis
streamlit run app.py
```

ブラウザで `http://localhost:8501` を開き、サイドバーで都道府県・市区町村を選んで「🚀 分析開始」。

### CLI (互換モード)

```bash
python main.py --config config/setagaya.yaml [--output ./output]
```

`run_pipeline()` は config の **ファイルパス (str)** と **dict** の両方を受け付ける (`main.py:27`)。Web アプリは `src/webapp.build_config_dict()` で dict を組み立てて直接渡す。

## にぎわいスコア計算式

```
vibrancy_score = flow_percentile × 0.6 + commercial_score × 0.4
commercial_score = min(commercial_count / 8 × 100, 100)
```

- **flow_percentile**: 半径 700m 以内の駅乗降客数の **単純合計** を自治体内でパーセンタイル正規化 (0-100)。距離減衰なし、「徒歩 8〜9 分の駅人流」を評価
- **commercial_count**: 半径 500m 以内の **目的地型** 商業施設数 (OSM 由来、コンビニ等の日常型は除外)
- ハード足切りなし、連続スコアで全公園をランキング

## ランク閾値

| ランク | 閾値 | 事業化判断 |
|---|---|---|
| A | ≥ 75 | 即事業化検討 |
| B | ≥ 50 | 条件次第で有望、サウンディング推奨 |
| C | ≥ 25 | 単独では難、バッジ組合せで検討 |
| D | < 25 | Park-PFI 単独は困難 |

## サブ評価バッジ (4 種)

| バッジキー | 判定基準 |
|---|---|
| `aging` | 供用開始から 30 年以上 |
| `childcare` | 半径 500m に子育て・教育施設 2 件以上 |
| `community_hub` | 公共施設 1 件以上 かつ 医療施設 1 件以上 近接 |
| `disaster` | 3,000m² 以上 かつ 公園種別 2/3/4 (近隣/地区/総合) |

しきい値は `config/default.yaml` の `badges` セクションで調整可能。

## Excel レポート構成 (9 シート)

1. 表紙
2. Executive Summary
3. 分析手法 (7 セクション: A 背景 / B 計算式 / C 目的地型商業 / D ランク閾値 / E バッジ設計 / F データソース / G 限界)
4. **にぎわいランキング** (主軸、全公園一覧 + バッジ列)
5. 歩行者流量
6. 周辺施設
7. 公園カルテ (Top N の詳細プロファイル)
8. バッジ別分析 (バッジごとの該当公園一覧 + 平均スコア)
9. データ品質

## データ構造 (`scored_parks` の各要素)

```python
{
    "name": str,
    "area_m2": float,
    "year_opened": int,
    "type_code": int,
    "type_name": str,
    "lat": float, "lon": float,
    "flow": {
        "normalized_score": float,    # 流量パーセンタイル (0-100)
        "raw_score": float,           # 半径700m内の乗降客数合計
        "station_count": int,
        "nearest_station": {...},
        "station_details": [...],
    },
    "surroundings": {
        # 各カテゴリごと: count, nearest, ...
        "commercial": {...}, "childcare": {...}, "education": {...},
        "elderly": {...}, "public": {...}, "medical": {...},
        "diversity_ratio": float,
        "total_count": int,
    },
    "vibrancy": {
        "score": float,               # にぎわいスコア (0-100)
        "rank": str,                  # A/B/C/D
        "flow_percentile": float,
        "commercial_count": int,
        "commercial_score": float,
    },
    "badges": {
        "aging": bool,
        "childcare": bool,
        "community_hub": bool,
        "disaster": bool,
    },
    "rank_position": int,             # 全体順位 (1-based)
}
```

## 設定ファイル

- `config/default.yaml` — デフォルトパラメータ (にぎわい重み、バッジしきい値、flow.max_radius=700、DPF/Overpass エンドポイント等)
- `config/setagaya.yaml` — CLI モード用のサンプル自治体設定 (世田谷区)

Web アプリは `setagaya.yaml` を使わず、`src/webapp.build_config_dict()` が選択された自治体から動的に dict を組み立てる。

## データソース

| データ | 提供元 | dataset_id / 用途 |
|---|---|---|
| 都市公園 | 国土数値情報 P13 (geospatial.jp) | `data/geojson/{pref}_parks.geojson` |
| 鉄道駅 | MLIT DPF API | `nlni_ksj-s12` (乗降客数 2023 年実績) |
| 福祉施設 | MLIT DPF API | `nlni_ksj-p14` |
| 医療施設 | MLIT DPF API | `nlni_ksj-p04` |
| 公共施設 | MLIT DPF API | `nlni_ksj-p02` |
| 商業施設 | OpenStreetMap (Overpass API) | 4 エンドポイントにフェイルオーバー |

## キャッシュ戦略

- `data/cache/dpf_{category}_{municipality}_{bbox_hash}.json` — DPF 施設データ (bbox 別)
- `data/cache/overpass_v2_{area_name}.json` — Overpass 商業データ (area_name 別)
- TTL: 168 時間 (7 日)
- Streamlit Community Cloud では FS が ephemeral のため、**世田谷区の DPF/Overpass キャッシュは git commit 済み** で初回高速化

## Web アプリ対応範囲

`src/webapp.py`:
- `available_prefectures()` — `data/geojson/` 配下の実在ファイルから対応都道府県を動的検出
- `load_municipalities()` — GeoJSON から `管理市区町村` ユニーク値を抽出
- `compute_bbox()` — 選択自治体の公園座標から bbox を自動計算 (margin 0.01°)
- `build_config_dict()` — `default.yaml` に選択情報を deep_merge して dict を返す

対応 GeoJSON: 東京都 / 神奈川県 / 埼玉県 / 千葉県 (計 4 ファイル、約 8.9 MB)

## 出力先

- `output/` — Excel (`.xlsx`) + Markdown (`.md`)、タイムスタンプ付き
- Streamlit UI からは bytes で直接ダウンロード可能

## 開発メモ

- 商業施設は目的地型のみフィルタ済み (コンビニ等の日常型は除外、約 43% 除外率)
- Overpass API はリトライ + 4 エンドポイントフェイルオーバー (`overpass-api.de` → `kumi.systems` → `private.coffee` → `openstreetmap.fr`)
- `report_generator.py` のヘルパー: `_write_row()`, `_style_header()`, `_auto_width()`, `_apply_print_settings()`, `_badge_cell_value()`, `RANK_FILLS`, `BADGE_ACTIVE_FILL`
- バッジ定数: `src/vibrancy_evaluator.py` の `BADGE_KEYS`, `BADGE_LABELS`, `BADGE_MARK="●"`
- Streamlit Community Cloud デプロイ手順は `README.md` 参照

## 歴史的経緯

- **v1**: 5 軸複合スコア (flow 30% + facility_mix 25% + condition 20% + area 15% + access 10%) + 5 類型分類 (老朽/子育て/にぎわい/防災/地域拠点)
- **v2**: スコア競合により「にぎわい創出型」が primary 判定 1 件のみに埋没する問題が発覚 → 北谷公園 (渋谷区) 現地調査の知見に基づき **にぎわい 1 軸 + 4 バッジ** に再設計
- **v3**: CLI から Streamlit Web アプリ化、1 都 3 県対応
- **v4**: 流量モデルを距離減衰 (exp(-d/400), 800m 半径) から **700m 半径の単純合計** に簡素化。北谷公園 (渋谷駅 623m) のような好立地を正しく捕捉するため 500m → 700m に拡張
