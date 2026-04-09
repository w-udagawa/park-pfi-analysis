# CLAUDE.md — Park-PFI Analysis

## プロジェクト概要

都市公園の Park-PFI（公募設置管理制度）ポテンシャルを分析するPythonツール。歩行者流量・周辺施設・老朽度等の多軸評価により、PFI導入に適した公園を自治体単位でランキングする。

## アーキテクチャ

```
main.py  (CLI エントリポイント)
  ├── src/config_loader.py       # YAML設定読み込み
  ├── src/data_collector.py      # GeoJSON + MLIT DPF + Overpass API データ収集
  ├── src/data_validator.py      # データ品質診断
  ├── src/pedestrian_flow.py     # 駅乗降客数ベースの流量スコアリング
  ├── src/surrounding_analysis.py # 周辺施設6カテゴリ分析
  ├── src/pfi_classifier.py      # PFI 5類型分類
  ├── src/scoring.py             # 5軸複合スコアリング (A/B/C/Dランク)
  └── src/report_generator.py    # Excel (11シート) + Markdown レポート
```

## 実行方法

```bash
cd /mnt/c/ClaudeWork/park-pfi-analysis
python main.py --config config/setagaya.yaml [--output ./output]
```

## PFI 5類型

| 類型 | キー | 説明 |
|---|---|---|
| 老朽再生型 | `aging_renewal` | 老朽化施設の更新 |
| 子育て支援型 | `childcare_support` | 子育て施設との連携 |
| にぎわい創出型 | `vibrancy_creation` | 商業施設・集客による活性化 |
| 防災公園型 | `disaster_prevention` | 防災拠点としての活用 |
| 地域拠点型 | `community_hub` | 地域コミュニティの中心 |

## Excel レポート構成 (11シート)

1. 表紙
2. Executive Summary
3. 分析手法
4. サマリー
5. 全公園ランキング
6. 類型別分析
7. **にぎわい創出ポテンシャル** — にぎわいスコア>0の公園一覧（Primary類型に関わらず）
8. 歩行者流量
9. 周辺施設
10. 公園カルテ
11. データ品質

## データ構造 (`scored_parks` の各要素)

```python
{
    "name": str,
    "area_m2": float,
    "classification": {
        "primary_type": str,           # PFI類型キー
        "primary_type_name": str,      # 日本語名
        "scores": {                    # 各類型スコア (0-100)
            "aging_renewal": float,
            "childcare_support": float,
            "vibrancy_creation": float,
            "disaster_prevention": float,
            "community_hub": float,
        }
    },
    "flow": {
        "normalized_score": float,     # 流量パーセンタイル (0-100)
        "raw_score": float,
        "nearest_station": {...},
    },
    "surroundings": {
        "commercial": {"count": int, ...},
        # childcare, education, elderly, public, medical
    },
    "scoring": {
        "total_score": float,          # 総合スコア
        "rank": str,                   # A/B/C/D
    },
}
```

## 設定ファイル

- `config/setagaya.yaml` — 世田谷区設定（bbox, GeoJSONパス, フィルタ条件）

## 出力先

- `output/` — Excel・Markdownレポート（タイムスタンプ付き）

## 開発メモ

- 商業施設は目的地型のみフィルタ済み（コンビニ等の日常型は除外、約43%除外率）
- にぎわい創出型がprimaryになる公園は1件のみ（スコア競合のため）→ Sheet 7 で別途可視化
- `report_generator.py` のヘルパー: `_write_row()`, `_style_header()`, `_auto_width()`, `_apply_print_settings()`
