"""Surrounding facility analysis with 6-category classification."""

from typing import Any, Dict, List

from .geo_utils import points_within_radius

# 6 facility categories for surrounding analysis
CATEGORIES = [
    "commercial",    # 商業施設 (shops, restaurants, cafes)
    "childcare",     # 子育て関連 (kindergarten, childcare, nursery)
    "education",     # 教育施設 (schools)
    "elderly",       # 高齢者関連 (nursing homes, elderly care)
    "public",        # 公共施設 (P02)
    "medical",       # 医療施設 (P33)
]

CATEGORY_NAMES = {
    "commercial": "商業施設",
    "childcare": "子育て関連",
    "education": "教育施設",
    "elderly": "高齢者関連",
    "public": "公共施設",
    "medical": "医療施設",
}


def _merge_facility_lists(facilities: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """Merge DPF and Overpass facility data into unified 6 categories.

    DPF welfare (P14) facilities are split into childcare/elderly based on facility_type.
    """
    merged: Dict[str, List[Dict]] = {cat: [] for cat in CATEGORIES}

    # Commercial from Overpass
    merged["commercial"] = facilities.get("commercial", [])

    # Childcare/Elderly: DPF welfare (P14) split by major_code
    # 05 = 児童福祉施設 (childcare), 99 = その他 (mostly elderly)
    welfare = facilities.get("welfare", [])
    for f in welfare:
        major_code = f.get("major_code", "")
        if major_code == "05":
            merged["childcare"].append(f)
        elif major_code == "99":
            merged["elderly"].append(f)
    merged["childcare"].extend(facilities.get("childcare_osm", []))

    # Education from Overpass
    merged["education"] = facilities.get("education", [])

    # Elderly: DPF welfare (elderly types) + Overpass elderly
    merged["elderly"].extend(facilities.get("elderly_osm", []))

    # Public from DPF (P02)
    merged["public"] = facilities.get("public", [])

    # Medical from DPF (P33)
    merged["medical"] = facilities.get("medical", [])

    return merged


def analyze_park_surroundings(
    park: Dict[str, Any],
    merged_facilities: Dict[str, List[Dict]],
    radius: float = 500,
) -> Dict[str, Any]:
    """Analyze surrounding facilities for a single park.

    Returns category counts and details within radius.
    """
    result = {}
    total_count = 0

    for cat in CATEGORIES:
        facilities = merged_facilities.get(cat, [])
        nearby = points_within_radius(park["lat"], park["lon"], facilities, radius)
        count = len(nearby)
        total_count += count

        nearest = None
        if nearby:
            f, d = nearby[0]
            nearest = {"name": f.get("name", "不明"), "distance_m": round(d)}

        result[cat] = {
            "count": count,
            "nearest": nearest,
            "facilities": [
                {"name": f.get("name", ""), "distance_m": round(d)}
                for f, d in nearby[:10]  # Top 10 nearest
            ],
        }

    result["total_count"] = total_count

    # Diversity score: how many categories have at least 1 facility
    categories_present = sum(1 for cat in CATEGORIES if result[cat]["count"] > 0)
    result["diversity"] = categories_present
    result["diversity_ratio"] = round(categories_present / len(CATEGORIES), 2)

    return result


def analyze_all_surroundings(
    parks: List[Dict[str, Any]],
    facilities: Dict[str, List[Dict]],
    config: dict,
) -> Dict[str, Dict[str, Any]]:
    """Analyze surrounding facilities for all parks.

    Returns dict keyed by park name.
    """
    radius = config["facility"]["radius"]
    merged = _merge_facility_lists(facilities)

    print(f"  Merged facility counts: " + ", ".join(
        f"{CATEGORY_NAMES[c]}={len(merged[c])}" for c in CATEGORIES
    ))

    results = {}
    for park in parks:
        results[park["name"]] = analyze_park_surroundings(park, merged, radius)

    return results
