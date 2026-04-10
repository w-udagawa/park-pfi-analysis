"""Park-PFI にぎわい創出ポテンシャル分析 — Streamlit Webアプリ。

起動: streamlit run app.py
"""

import os
import sys
from pathlib import Path

# Add project root to path so `src` imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import altair as alt
import pandas as pd
import streamlit as st

from main import run_pipeline
from src.config_loader import load_default_config
from src.webapp import (
    PREFECTURE_GEOJSON,
    available_prefectures,
    build_config_dict,
    load_municipalities,
)

GEOJSON_DIR = Path(__file__).parent / "data" / "geojson"
OUTPUT_DIR = Path(__file__).parent / "output"

st.set_page_config(
    page_title="Park-PFI にぎわい分析",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Sidebar: 自治体選択
# ---------------------------------------------------------------------------

st.sidebar.title("🌳 Park-PFI 分析")
st.sidebar.caption("にぎわい創出ポテンシャル")

prefs = available_prefectures(GEOJSON_DIR)
missing_prefs = [p for p in PREFECTURE_GEOJSON if p not in prefs]

if not prefs:
    st.sidebar.error("GeoJSON ファイルが見つかりません。data/geojson/ に配置してください。")
    st.stop()

prefecture = st.sidebar.selectbox("都道府県", prefs, index=0)

try:
    municipalities = load_municipalities(prefecture, GEOJSON_DIR)
except Exception as e:
    st.sidebar.error(f"自治体リストの読み込みに失敗: {e}")
    st.stop()

default_muni = "世田谷区" if "世田谷区" in municipalities else municipalities[0]
municipality = st.sidebar.selectbox(
    "市区町村",
    municipalities,
    index=municipalities.index(default_muni),
)

st.sidebar.markdown("---")
run_button = st.sidebar.button("🚀 分析開始", type="primary", use_container_width=True)

if missing_prefs:
    st.sidebar.warning(
        "未配置の GeoJSON: " + ", ".join(missing_prefs)
        + "\n\n国土数値情報「都市公園データ (A33)」からダウンロードして "
        "`data/geojson/{pref}_parks.geojson` に配置してください。"
    )

st.sidebar.markdown("---")
st.sidebar.caption(
    "**データソース**\n"
    "- 国土数値情報 都市公園 (GeoJSON)\n"
    "- MLIT DPF API (駅/施設)\n"
    "- OpenStreetMap (商業施設)\n"
)


# ---------------------------------------------------------------------------
# Main: 分析実行
# ---------------------------------------------------------------------------

st.title(f"{prefecture} {municipality}")
st.caption("Park-PFI にぎわい創出ポテンシャル分析")

if run_button:
    try:
        default_cfg = load_default_config()
    except Exception as e:
        st.error(f"設定読み込みに失敗しました: {e}")
        st.stop()

    if not default_cfg.get("dpf", {}).get("api_key"):
        st.error(
            "MLIT DPF API キーが設定されていません。"
            "`.streamlit/secrets.toml` に `MLIT_API_KEY` を設定するか、"
            "環境変数 `MLIT_API_KEY` を定義してください。"
        )
        st.stop()

    try:
        cfg = build_config_dict(prefecture, municipality, GEOJSON_DIR, default_cfg)
    except Exception as e:
        st.error(f"設定組み立てに失敗しました: {e}")
        st.stop()

    progress_bar = st.progress(0.0, text="準備中...")
    log_box = st.empty()
    logs: list[str] = []

    def on_progress(step: str, ratio: float):
        progress_bar.progress(min(max(ratio, 0.0), 1.0), text=f"[{int(ratio*100)}%] {step}")
        logs.append(f"[{int(ratio*100)}%] {step}")
        log_box.code("\n".join(logs[-10:]), language=None)

    with st.status(f"{municipality} を分析中...", expanded=True) as status:
        try:
            scored_parks, excel_path, md_path = run_pipeline(
                cfg,
                output_dir=str(OUTPUT_DIR),
                progress_callback=on_progress,
            )
            status.update(label=f"分析完了 ({len(scored_parks)}公園)", state="complete")
        except Exception as e:
            status.update(label=f"エラー: {e}", state="error")
            st.exception(e)
            st.stop()

    st.session_state["scored_parks"] = scored_parks
    st.session_state["excel_path"] = excel_path
    st.session_state["md_path"] = md_path
    st.session_state["municipality"] = municipality
    st.session_state["prefecture"] = prefecture


# ---------------------------------------------------------------------------
# Results display
# ---------------------------------------------------------------------------

if "scored_parks" not in st.session_state:
    st.info("👈 サイドバーで自治体を選び「分析開始」を押してください。")
    st.markdown(
        """
        ### このアプリでできること
        - 選択した市区町村の都市公園を **にぎわい創出ポテンシャル** で一括ランキング
        - 老朽/子育て/地域拠点/防災 の **4バッジ** で Park-PFI 活用シナリオを可視化
        - Top 公園の詳細プロファイル・周辺駅・施設構成を確認
        - 分析結果を **Excel / Markdown** でダウンロード

        ### 評価手法
        - **にぎわいスコア = 流量%ile × 0.6 + 商業スコア × 0.4**（0〜100連続スコア）
        - 半径700m圏内の駅乗降客数の合計を自治体内でパーセンタイル正規化
        - 目的地型商業（飲食・物販・カフェ等）の半径500m圏内密度

        詳細は分析後の「評価基準・解説」タブを参照。
        """
    )
    st.stop()

parks = st.session_state["scored_parks"]
n = len(parks)

# KPI カード
col1, col2, col3, col4 = st.columns(4)
col1.metric("対象公園数", n)
col2.metric("Top スコア", f"{parks[0]['vibrancy']['score']:.1f}")
a_rank = sum(1 for p in parks if p["vibrancy"]["rank"] == "A")
col3.metric("Aランク公園", f"{a_rank} ({a_rank / max(n, 1) * 100:.0f}%)")
avg = sum(p["vibrancy"]["score"] for p in parks) / max(n, 1)
col4.metric("平均スコア", f"{avg:.1f}")

st.markdown("---")

# タブ
tab_rank, tab_dist, tab_profile, tab_dl, tab_method = st.tabs([
    "📊 にぎわいランキング",
    "📈 分布チャート",
    "🏞 公園プロファイル",
    "📥 レポートDL",
    "📚 評価基準・解説",
])

# -----------------------------------------------------------------
# Tab 1: ランキング
# -----------------------------------------------------------------
with tab_rank:
    st.subheader(f"全{n}公園のにぎわいランキング")

    rank_filter = st.multiselect(
        "ランクで絞り込み",
        options=["A", "B", "C", "D"],
        default=["A", "B", "C", "D"],
    )

    badge_filter = st.multiselect(
        "バッジで絞り込み（ANDで該当）",
        options=["老朽", "子育て", "地域拠点", "防災"],
        default=[],
    )
    badge_keymap = {
        "老朽": "aging", "子育て": "childcare",
        "地域拠点": "community_hub", "防災": "disaster",
    }

    filtered = [
        p for p in parks
        if p["vibrancy"]["rank"] in rank_filter
        and all(p["badges"].get(badge_keymap[b]) for b in badge_filter)
    ]

    df = pd.DataFrame([{
        "順位": p["rank_position"],
        "公園名": p["name"],
        "にぎわい": round(p["vibrancy"]["score"], 1),
        "ランク": p["vibrancy"]["rank"],
        "流量%ile": round(p["vibrancy"]["flow_percentile"], 1),
        "700m乗降合計": int(p.get("flow", {}).get("raw_score", 0)),
        "商業数": p["vibrancy"]["commercial_count"],
        "老朽": "●" if p["badges"]["aging"] else "",
        "子育て": "●" if p["badges"]["childcare"] else "",
        "地域拠点": "●" if p["badges"]["community_hub"] else "",
        "防災": "●" if p["badges"]["disaster"] else "",
        "面積(m²)": int(p["area_m2"]),
        "種別": p["type_name"],
        "開園年": p.get("year_opened") or "",
    } for p in filtered])

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=600,
        column_config={
            "にぎわい": st.column_config.ProgressColumn(
                "にぎわい", format="%.1f", min_value=0, max_value=100
            ),
            "流量%ile": st.column_config.NumberColumn(format="%.1f"),
            "700m乗降合計": st.column_config.NumberColumn(format="%d"),
            "面積(m²)": st.column_config.NumberColumn(format="%d"),
        },
    )
    st.caption(f"表示: {len(filtered)} / {n} 公園")

# -----------------------------------------------------------------
# Tab 2: 分布チャート
# -----------------------------------------------------------------
with tab_dist:
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("にぎわいランク分布")
        rank_df = pd.DataFrame({
            "ランク": ["A", "B", "C", "D"],
            "公園数": [sum(1 for p in parks if p["vibrancy"]["rank"] == r) for r in "ABCD"],
        })
        chart = alt.Chart(rank_df).mark_bar().encode(
            x=alt.X("ランク:N", sort=["A", "B", "C", "D"]),
            y="公園数:Q",
            color=alt.Color(
                "ランク:N",
                scale=alt.Scale(
                    domain=["A", "B", "C", "D"],
                    range=["#548235", "#BF8F00", "#C55A11", "#A5A5A5"],
                ),
                legend=None,
            ),
            tooltip=["ランク", "公園数"],
        ).properties(height=300)
        st.altair_chart(chart, use_container_width=True)

    with col_b:
        st.subheader("サブ評価バッジ分布")
        badge_df = pd.DataFrame({
            "バッジ": ["老朽", "子育て", "地域拠点", "防災"],
            "公園数": [
                sum(1 for p in parks if p["badges"]["aging"]),
                sum(1 for p in parks if p["badges"]["childcare"]),
                sum(1 for p in parks if p["badges"]["community_hub"]),
                sum(1 for p in parks if p["badges"]["disaster"]),
            ],
        })
        bchart = alt.Chart(badge_df).mark_bar().encode(
            x=alt.X("バッジ:N", sort=["老朽", "子育て", "地域拠点", "防災"]),
            y="公園数:Q",
            color=alt.Color(
                "バッジ:N",
                scale=alt.Scale(
                    domain=["老朽", "子育て", "地域拠点", "防災"],
                    range=["#548235", "#BF8F00", "#2B5797", "#C55A11"],
                ),
                legend=None,
            ),
            tooltip=["バッジ", "公園数"],
        ).properties(height=300)
        st.altair_chart(bchart, use_container_width=True)

    st.subheader("にぎわいスコアのヒストグラム")
    score_df = pd.DataFrame({"score": [p["vibrancy"]["score"] for p in parks]})
    hist = alt.Chart(score_df).mark_bar().encode(
        x=alt.X("score:Q", bin=alt.Bin(maxbins=20), title="にぎわいスコア"),
        y=alt.Y("count()", title="公園数"),
    ).properties(height=250)
    st.altair_chart(hist, use_container_width=True)

# -----------------------------------------------------------------
# Tab 3: 公園プロファイル
# -----------------------------------------------------------------
with tab_profile:
    st.subheader("公園カルテ（Top 公園の詳細）")
    names = [f"#{p['rank_position']} {p['name']} (スコア {p['vibrancy']['score']:.1f})"
             for p in parks[:50]]
    idx = st.selectbox("公園を選択", range(len(names)), format_func=lambda i: names[i])
    p = parks[idx]

    col_l, col_r = st.columns([1, 1])
    with col_l:
        v = p["vibrancy"]
        flow_data = p.get("flow", {})
        nearest_station = flow_data.get("nearest_station")
        total_ridership = int(flow_data.get("raw_score", 0))
        station_count = flow_data.get("station_count", 0)

        st.metric("にぎわいスコア", f"{v['score']:.1f}", f"ランク {v['rank']}")

        # 最寄駅・700m合計乗降のサマリ
        if nearest_station:
            st.write(
                f"**最寄駅**: {nearest_station['name']} "
                f"({nearest_station['distance_m']}m、乗降 {nearest_station['ridership']:,})"
            )
        else:
            st.write("**最寄駅**: 700m圏内になし")
        st.write(
            f"**700m圏内 合計乗降客数**: {total_ridership:,} 人 "
            f"({station_count}駅)"
        )

        st.write(f"**面積**: {p['area_m2']:,} m²")
        st.write(f"**種別**: {p['type_name']}")
        st.write(f"**開園年**: {p.get('year_opened') or '不明'}")

        active = [b for b in ["老朽", "子育て", "地域拠点", "防災"]
                  if p["badges"][{"老朽": "aging", "子育て": "childcare",
                                   "地域拠点": "community_hub", "防災": "disaster"}[b]]]
        st.write(f"**バッジ**: {'・'.join(active) if active else '該当なし'}")

        if p.get("lat") and p.get("lon"):
            earth_url = f"https://earth.google.com/web/@{p['lat']},{p['lon']},100a,500d,35y,0h,60t,0r"
            st.markdown(f"[🌏 Google Earth で見る]({earth_url})")

    with col_r:
        st.write("**にぎわいスコア内訳**")
        breakdown = pd.DataFrame({
            "項目": ["流量寄与", "商業寄与"],
            "スコア": [
                round(v["flow_percentile"] * 0.6, 1),
                round(v["commercial_score"] * 0.4, 1),
            ],
        })
        bchart2 = alt.Chart(breakdown).mark_bar().encode(
            x=alt.X("スコア:Q", scale=alt.Scale(domain=[0, 60])),
            y=alt.Y("項目:N", sort=None),
            color=alt.Color("項目:N", legend=None),
            tooltip=["項目", "スコア"],
        ).properties(height=150)
        st.altair_chart(bchart2, use_container_width=True)

        st.caption(
            f"流量%ile: {v['flow_percentile']:.1f} / "
            f"商業数: {v['commercial_count']} "
            f"(スコア: {v['commercial_score']:.1f})"
        )

    st.markdown("---")
    col_s, col_f = st.columns(2)
    with col_s:
        st.write("**700m圏内の駅**")
        stations = p.get("flow", {}).get("station_details", [])
        if stations:
            st.write(
                f"合計乗降客数: **{total_ridership:,} 人** / 駅数: {station_count}"
            )
            for st_info in stations[:5]:
                st.write(
                    f"- {st_info['name']} "
                    f"({st_info['distance_m']}m、乗降{st_info['ridership']:,})"
                )
        else:
            st.write("700m圏内に駅なし")

    with col_f:
        st.write("**周辺施設（半径500m）**")
        surr = p.get("surroundings", {})
        cat_names = {
            "commercial": "商業", "childcare": "子育て",
            "education": "教育", "elderly": "高齢者",
            "public": "公共", "medical": "医療",
        }
        for cat, label in cat_names.items():
            count = surr.get(cat, {}).get("count", 0)
            st.write(f"- {label}: {count}件")

# -----------------------------------------------------------------
# Tab 4: ダウンロード
# -----------------------------------------------------------------
with tab_dl:
    excel_path = st.session_state.get("excel_path")
    md_path = st.session_state.get("md_path")

    if excel_path and Path(excel_path).exists():
        with open(excel_path, "rb") as f:
            st.download_button(
                "📥 Excel レポート (9シート)",
                f.read(),
                file_name=Path(excel_path).name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    if md_path and Path(md_path).exists():
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        st.download_button(
            "📄 Markdown レポート",
            md_content,
            file_name=Path(md_path).name,
            mime="text/markdown",
        )
        with st.expander("Markdown プレビュー"):
            st.markdown(md_content)

# -----------------------------------------------------------------
# Tab 5: 評価基準・解説
# -----------------------------------------------------------------
with tab_method:
    st.markdown("""
## A. 評価軸選定の背景

本分析は **Park-PFI（公募設置管理制度）導入ポテンシャル** を「にぎわい創出」単一軸で定量化しています。

1. **北谷公園（渋谷区）現地調査**: 事業者・利用者インタビューから、Park-PFI の成否は「**人流の量**」と「**人流の属性（周辺建物用途）**」に強く依存することが確認された
2. 従来の5類型分類（老朽/子育て/にぎわい/防災/地域拠点）では類型間のスコア競合により、本来にぎわい創出型として有望な公園が埋もれていた
3. そこで **にぎわいスコアをメイン軸、他要素は●バッジ** でサブ評価する構造に変更

---

## B. にぎわいスコア計算式

```
vibrancy_score = flow_percentile × 0.6 + commercial_score × 0.4
commercial_score = min(commercial_count / 8 × 100, 100)
```

### 重み配分の根拠

- **flow_percentile × 0.6**: 「人が通らない場所に施設を作っても稼働しない」という事業者サイドの最大制約を反映。人流は Park-PFI の必要条件
- **commercial_score × 0.4**: 「目的意識を持って訪れる人流」の補完指標。飲食・物販施設集積地は公園利用が食事・買い物の延長に組み込まれやすい

### commercial_divisor = 8 の根拠

世田谷区の商業集積上位エリア（三軒茶屋・下北沢・二子玉川周辺）における半径500m圏内の目的地型商業数の水準（約8件前後）を満点とするスケール設計。

### ハード足切り廃止の理由

旧実装では「流量上位40%」かつ「商業2件以上」のAND条件で約90%の公園が0点だった。連続スコア化することで低スコア帯の公園もバッジとの組合せで活用検討できる。

### パーセンタイル正規化

flow_percentile は **半径700m圏内の駅乗降客数の合計** を自治体内で順位化した相対指標。自治体間ではなく「その自治体内での人流ランク」を測る。距離減衰関数は採用せず、各駅の乗降客数を等しく加算する単純合計とした。

**700m半径を採用した理由**: (1) 徒歩8〜9分の実用的な駅アクセス圏に相当し、ターミナル駅から少し離れた好立地公園（例: 北谷公園←渋谷駅623m）の人流を正しく捕捉できる。(2) 500mでは渋谷駅クラスの大型駅からの人流が評価に反映されないケースがあったため拡張。

---

## C. 「目的地型商業」の定義

| 対象 | 除外 |
|---|---|
| レストラン・カフェ・バー・居酒屋 | コンビニ |
| 書店・衣料品・電化製品 | ファストフード |
| 雑貨・ギフト・ベーカリー | ドラッグストア |
| 美容・エンタメ施設 | スーパーマーケット |

**除外の根拠**: 日常型は経路上の「ついで利用」が中心で公園訪問のインセンティブにならない。南池袋公園・北谷公園等の成功事例では、目的意識のある来訪者が滞在時間を延ばす構造が共通する。

データソース: OpenStreetMap Overpass API（`DESTINATION_SHOP_TYPES` でフィルタ、約43%が除外）

---

## D. ランク閾値の意味

| ランク | 閾値 | 解釈 |
|---|---|---|
| **A** | ≥ 75 | 即事業化検討レベル。Park-PFI 単独でも収益性が見込める |
| **B** | ≥ 50 | 条件次第で有望。サウンディング調査推奨 |
| **C** | ≥ 25 | 単独では難。バッジとの組合せで活用検討 |
| **D** | < 25 | Park-PFI 単独は困難。指定管理・PFS 等を検討 |

---

## E. サブ評価バッジの設計

バッジはメイン軸を単一化する一方、導入検討時の文脈情報を失わないための補助指標です。

| バッジ | 判定基準 | Park-PFI 活用シナリオ |
|---|---|---|
| **老朽** | 供用開始から30年以上 | 老朽施設更新と組合せ、自治体財政負担を軽減 |
| **子育て** | 半径500mに子育て・教育施設2件以上 | 親子向けカフェ・屋内プレイ・体験型施設候補 |
| **地域拠点** | 公共1件以上 かつ 医療1件以上近接 | 多世代交流・集会所・健康増進拠点連携 |
| **防災** | 3,000m²以上 かつ 近隣/地区/総合公園 | 平時にぎわい・災害時拠点の複合スキーム |

---

## F. 限界と注意点

- **OSM カバレッジ**: 地域ごとのメンテナンス頻度に差あり、地方都市では商業数が過小評価される可能性
- **乗降客数は2023年実績**: 再開発・新線開業等の最新変化は未反映
- **面積下限 960m²**: 北谷公園（約960m²）事業実績を参考にした目安
- **バッジしきい値**: 世田谷区向け標準設定。人口密度の異なる自治体では調整推奨
- **分類の自動化**: OSM タグベースの機械的判定。個店レベルでは誤分類可能性あり
- **机上スクリーニング**: 実際の事業化判断には現地調査・合意形成・サウンディング調査が必要
    """)
