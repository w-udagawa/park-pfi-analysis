"""にぎわい創出ポテンシャル評価。

全公園に連続的な「にぎわいスコア」を付与し、老朽・子育て・地域拠点・防災の
4バッジをサブ評価として計算する。
"""

from datetime import datetime
from typing import Any, Dict, List

BADGE_KEYS = ["aging", "childcare", "community_hub", "disaster"]
BADGE_LABELS = {
    "aging": "老朽",
    "childcare": "子育て",
    "community_hub": "地域拠点",
    "disaster": "防災",
}
BADGE_MARK = "●"


def evaluate_vibrancy(
    park: Dict,
    surroundings: Dict,
    flow_data: Dict,
    config: dict,
) -> Dict[str, Any]:
    """にぎわいスコアを計算する（足切りなし、0〜100の連続スコア）。

    score = flow_percentile * flow_weight + commercial_score * commercial_weight
      where commercial_score = min(commercial_count / divisor * 100, 100)
    """
    params = config["vibrancy"]
    flow_weight = params["flow_weight"]
    commercial_weight = params["commercial_weight"]
    divisor = params["commercial_divisor"]

    flow_percentile = flow_data.get("normalized_score", 0) or 0
    commercial_count = surroundings.get("commercial", {}).get("count", 0) or 0

    commercial_score = min(commercial_count / divisor * 100, 100) if divisor > 0 else 0.0
    score = flow_percentile * flow_weight + commercial_score * commercial_weight
    score = round(min(score, 100), 1)

    ranks = config["ranks"]
    if score >= ranks["A"]:
        rank = "A"
    elif score >= ranks["B"]:
        rank = "B"
    elif score >= ranks["C"]:
        rank = "C"
    else:
        rank = "D"

    return {
        "score": score,
        "rank": rank,
        "flow_percentile": round(flow_percentile, 1),
        "commercial_count": commercial_count,
        "commercial_score": round(commercial_score, 1),
    }


def compute_badges(
    park: Dict,
    surroundings: Dict,
    config: dict,
) -> Dict[str, bool]:
    """サブ評価バッジを計算する。

    - aging: 築年数 >= aging_years
    - childcare: childcare + education >= childcare_min
    - community_hub: public >= public_min AND medical >= medical_min
    - disaster: area >= disaster_min_area AND type_code in disaster_park_types
    """
    b = config["badges"]
    current_year = datetime.now().year

    # 老朽バッジ
    year = park.get("year_opened")
    if year and year > 0:
        aging = (current_year - year) >= b["aging_years"]
    else:
        aging = False

    # 子育てバッジ
    childcare_count = surroundings.get("childcare", {}).get("count", 0) or 0
    education_count = surroundings.get("education", {}).get("count", 0) or 0
    childcare = (childcare_count + education_count) >= b["childcare_min"]

    # 地域拠点バッジ
    public_count = surroundings.get("public", {}).get("count", 0) or 0
    medical_count = surroundings.get("medical", {}).get("count", 0) or 0
    community_hub = (
        public_count >= b["community_public_min"]
        and medical_count >= b["community_medical_min"]
    )

    # 防災バッジ
    area = park.get("area_m2", 0) or 0
    type_code = park.get("type_code", 0)
    disaster = (
        area >= b["disaster_min_area"]
        and type_code in b["disaster_park_types"]
    )

    return {
        "aging": aging,
        "childcare": childcare,
        "community_hub": community_hub,
        "disaster": disaster,
    }


def evaluate_all_parks(
    parks: List[Dict],
    surroundings_all: Dict[str, Dict],
    flow_all: Dict[str, Dict],
    config: dict,
) -> List[Dict[str, Any]]:
    """全公園を評価して、にぎわいスコア降順でソートされたリストを返す。"""
    scored = []
    for park in parks:
        name = park["name"]
        flow_data = flow_all.get(name, {})
        surroundings = surroundings_all.get(name, {})

        vibrancy = evaluate_vibrancy(park, surroundings, flow_data, config)
        badges = compute_badges(park, surroundings, config)

        scored.append({
            **park,
            "flow": flow_data,
            "surroundings": surroundings,
            "vibrancy": vibrancy,
            "badges": badges,
        })

    scored.sort(key=lambda p: -p["vibrancy"]["score"])

    for i, p in enumerate(scored):
        p["rank_position"] = i + 1

    return scored
