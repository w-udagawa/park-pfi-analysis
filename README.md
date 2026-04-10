# Park-PFI にぎわい創出ポテンシャル分析

東京都・神奈川県・埼玉県・千葉県の任意の市区町村について、都市公園の **Park-PFI（公募設置管理制度）導入ポテンシャル** を「にぎわい創出」軸で定量評価する Streamlit Web アプリ。

- **メイン軸**: にぎわいスコア（0–100 の連続値）= 流量%ile × 0.6 + 商業スコア × 0.4
- **サブ評価**: 老朽 / 子育て / 地域拠点 / 防災 の4バッジ（●/空白）
- **出力**: 9シート Excel レポート + Markdown ダイジェスト

---

## ローカル実行

### 1. 依存インストール

```bash
pip install -r requirements.txt
```

### 2. API キー設定

MLIT DPF API キーが必要です。以下のいずれかの方法で設定:

**方法A**: `.streamlit/secrets.toml` を作成（Streamlit 環境で推奨）

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# ファイルを編集して MLIT_API_KEY を実値に
```

**方法B**: 環境変数

```bash
export MLIT_API_KEY="your-key-here"
```

### 3. 起動

```bash
streamlit run app.py
```

ブラウザで `http://localhost:8501` を開く。サイドバーで都道府県・市区町村を選択し「🚀 分析開始」を押下。初回は API 呼び出しで 15〜30 秒、2回目以降はキャッシュヒットで 1〜2 秒。

### CLI モード（互換性維持）

```bash
python main.py --config config/setagaya.yaml
```

---

## Streamlit Community Cloud へのデプロイ

### 事前準備

- GitHub アカウント
- Streamlit Community Cloud アカウント（無料、GitHub 連携）
- MLIT DPF API キー

### 手順

#### 1. GitHub リポジトリ作成

GitHub で新規リポジトリを作成（public/private どちらでも可）。リポジトリ名は任意（例: `park-pfi-analysis`）。

#### 2. リモート追加 & 初回 push

ローカルリポジトリは既に `git init` + 初回コミット済みです。

```bash
cd /mnt/c/ClaudeWork/park-pfi-analysis
git remote add origin https://github.com/<YOUR_USERNAME>/<REPO_NAME>.git
git branch -M main
git push -u origin main
```

#### 3. Streamlit Community Cloud にデプロイ

1. https://share.streamlit.io/ にサインインし **"New app"** をクリック
2. 下記を指定:
   - **Repository**: `<YOUR_USERNAME>/<REPO_NAME>`
   - **Branch**: `main`
   - **Main file path**: `app.py`
3. **"Advanced settings" → "Secrets"** に以下を貼り付け:
   ```toml
   MLIT_API_KEY = "your-actual-api-key-here"
   ```
4. **"Deploy!"** をクリック。初回ビルドは 2〜3 分程度

#### 4. 動作確認

デプロイ後の URL にアクセスし、「東京都 / 世田谷区」を選択して分析実行できることを確認。

### Community Cloud の制約事項

- **ファイルシステム ephemeral**: `data/cache/` はアプリ再起動時に消える。初回利用時は 15〜30 秒の待ち時間が発生
- **スリープ**: 一定時間アクセスがないとアプリがスリープ状態になる（初回アクセスで再起動、約 30 秒）
- **リソース**: 無料枠は 1GB RAM、1 CPU（本アプリの負荷では問題なし）
- **同時アクセス**: 複数人が同時に分析を実行するとキャッシュ書き込みで競合する可能性あり

---

## プロジェクト構成

```
park-pfi-analysis/
├── app.py                      # Streamlit エントリポイント
├── main.py                     # 分析パイプライン（CLI互換、run_pipeline関数）
├── requirements.txt            # Python 依存
├── runtime.txt                 # Python バージョン pin
├── config/
│   ├── default.yaml            # デフォルトパラメータ（スコア重み・バッジしきい値等）
│   └── setagaya.yaml           # CLI モード用サンプル設定
├── data/
│   ├── geojson/                # 1都3県の都市公園 GeoJSON
│   │   ├── tokyo_parks.geojson
│   │   ├── kanagawa_parks.geojson
│   │   ├── saitama_parks.geojson
│   │   └── chiba_parks.geojson
│   └── cache/                  # API キャッシュ（.gitignore 対象）
├── src/
│   ├── config_loader.py        # YAML読み込み + API キー解決
│   ├── data_collector.py       # MLIT DPF / Overpass API クライアント
│   ├── data_validator.py       # データ品質診断
│   ├── geo_utils.py            # Haversine / 距離計算
│   ├── pedestrian_flow.py      # 駅乗降客数ベースの流量スコア
│   ├── surrounding_analysis.py # 周辺施設分析（6カテゴリ）
│   ├── vibrancy_evaluator.py   # にぎわいスコア + バッジ判定
│   ├── report_generator.py     # Excel (9シート) + Markdown 生成
│   └── webapp.py               # Web アプリ用ヘルパー（自治体選択、bbox 計算、config 構築）
├── output/                     # 生成レポート（.gitignore 対象）
├── .streamlit/
│   ├── config.toml             # テーマ設定
│   └── secrets.toml.example    # API キー雛形（実体は .gitignore）
└── .gitignore
```

---

## データソース

| データ | 提供元 | 用途 |
|---|---|---|
| 都市公園 (P13) | 国土数値情報 | 公園位置・面積・種別・供用開始年 |
| 鉄道駅 (S12) | MLIT DPF API | 駅乗降客数（2023年実績） |
| 福祉施設 (P14) | MLIT DPF API | 子育て・高齢者施設 |
| 医療施設 (P04) | MLIT DPF API | 病院・診療所 |
| 公共施設 (P02) | MLIT DPF API | 公民館・図書館等 |
| 商業施設 | OpenStreetMap (Overpass API) | 目的地型商業（飲食・物販・カフェ等） |

---

## 評価手法の概要

### にぎわいスコア

```
vibrancy_score = flow_percentile × 0.6 + commercial_score × 0.4
commercial_score = min(commercial_count / 8 × 100, 100)
```

- **flow_percentile**: 半径700m以内の全駅の乗降客数を単純合計し、自治体内でパーセンタイル正規化 (0–100)
- **commercial_count**: 半径500m以内の **目的地型** 商業施設数（OpenStreetMap 由来）

ハード足切りなし。全公園に連続スコアを付与し、スコア降順でランキング。

### ランク閾値

| ランク | 閾値 | 解釈 |
|---|---|---|
| **A** | ≥ 75 | 即事業化検討レベル |
| **B** | ≥ 50 | 条件次第で有望、サウンディング推奨 |
| **C** | ≥ 25 | 単独では難、バッジ組合せで検討 |
| **D** | < 25 | Park-PFI 単独は困難 |

### サブ評価バッジ

| バッジ | 判定基準 |
|---|---|
| **老朽** | 供用開始から 30 年以上 |
| **子育て** | 半径 500m に子育て・教育施設 2 件以上 |
| **地域拠点** | 公共施設 1 件以上 かつ 医療施設 1 件以上 近接 |
| **防災** | 3,000m² 以上 かつ 近隣・地区・総合公園 |

詳細はアプリ内「📚 評価基準・解説」タブ、または Excel レポートの「分析手法」シート（7セクション）を参照。

---

## 評価手法の背景

本アプリは、渋谷区「北谷公園」（約960m²、Park-PFI 実施事例）の現地調査から得た知見に基づき、**人流の量と属性が Park-PFI 成否の鍵**であるという前提で設計されている。従来の5類型分類（老朽/子育て/にぎわい/防災/地域拠点）ではスコア競合により、実需要と一致しないランキングが出る問題があったため、**にぎわいスコア一本軸** に簡素化し、他要素は **バッジ** で併記する構造に変更した。
