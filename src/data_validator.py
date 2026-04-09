"""Data coverage diagnostics for multi-municipality deployment."""

from typing import Any, Dict, List


# Minimum thresholds for data quality warnings
MIN_STATIONS = 5
MIN_FACILITIES_PER_CATEGORY = 3
MIN_COMMERCIAL = 5  # フィルタ後の目的地型のみ
WARN_MISSING_COORDS_PCT = 5.0
WARN_MISSING_AREA_PCT = 10.0
WARN_MISSING_YEAR_PCT = 30.0

SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"


def validate_data_coverage(
    config: dict,
    parks: List[Dict],
    stations: List[Dict],
    facilities: Dict[str, List[Dict]],
) -> Dict[str, Any]:
    """Run data coverage diagnostics before analysis.

    Returns:
        dict with keys:
            - issues: list of {severity, category, message, detail}
            - coverage_scores: dict of category -> 0-100 score
            - summary: overall pass/warn/fail status
    """
    issues: List[Dict[str, str]] = []
    coverage_scores: Dict[str, float] = {}

    municipality = config["municipality"]["name"]

    # ---------------------------------------------------------------
    # 1. Park data quality
    # ---------------------------------------------------------------
    total_parks = len(parks)
    if total_parks == 0:
        issues.append({
            "severity": SEVERITY_HIGH,
            "category": "公園データ",
            "message": "公園が0件です",
            "detail": f"{municipality}のGeoJSONフィルタ結果が空です。filter_field/filter_valueを確認してください。",
        })
        coverage_scores["parks"] = 0
    else:
        # Coordinate completeness
        missing_coords = sum(1 for p in parks if not p.get("lat") or not p.get("lon"))
        coords_pct = missing_coords / total_parks * 100
        if coords_pct > WARN_MISSING_COORDS_PCT:
            issues.append({
                "severity": SEVERITY_HIGH,
                "category": "公園データ",
                "message": f"座標欠損: {missing_coords}/{total_parks}件 ({coords_pct:.1f}%)",
                "detail": "座標がない公園は空間分析から除外されます。",
            })

        # Area completeness
        missing_area = sum(1 for p in parks if not p.get("area_m2") or p["area_m2"] <= 0)
        area_pct = missing_area / total_parks * 100
        if area_pct > WARN_MISSING_AREA_PCT:
            issues.append({
                "severity": SEVERITY_MEDIUM,
                "category": "公園データ",
                "message": f"面積欠損: {missing_area}/{total_parks}件 ({area_pct:.1f}%)",
                "detail": "面積が不明な公園は面積適合性スコアが低下します。",
            })

        # Year completeness
        missing_year = sum(1 for p in parks if not p.get("year_opened") or p["year_opened"] <= 0)
        year_pct = missing_year / total_parks * 100
        if year_pct > WARN_MISSING_YEAR_PCT:
            issues.append({
                "severity": SEVERITY_MEDIUM,
                "category": "公園データ",
                "message": f"供用開始年欠損: {missing_year}/{total_parks}件 ({year_pct:.1f}%)",
                "detail": "供用開始年が不明な公園は老朽再生型の判定精度が低下します。",
            })

        park_completeness = 100 - (coords_pct * 0.4 + area_pct * 0.3 + year_pct * 0.3)
        coverage_scores["parks"] = max(0, round(park_completeness, 1))

    # ---------------------------------------------------------------
    # 2. Station data
    # ---------------------------------------------------------------
    station_count = len(stations)
    if station_count == 0:
        issues.append({
            "severity": SEVERITY_HIGH,
            "category": "駅データ (S12)",
            "message": "駅データが0件です",
            "detail": "DPF APIの接続・bbox範囲・データセットIDを確認してください。",
        })
        coverage_scores["stations"] = 0
    elif station_count < MIN_STATIONS:
        issues.append({
            "severity": SEVERITY_MEDIUM,
            "category": "駅データ (S12)",
            "message": f"駅データが少数: {station_count}件（推奨: {MIN_STATIONS}件以上）",
            "detail": "歩行者流量スコアの分散が小さくなる可能性があります。",
        })
        coverage_scores["stations"] = round(station_count / MIN_STATIONS * 100, 1)
    else:
        # Check ridership availability
        no_ridership = sum(1 for s in stations if not s.get("ridership") or s["ridership"] <= 0)
        ridership_pct = (1 - no_ridership / station_count) * 100
        coverage_scores["stations"] = round(ridership_pct, 1)
        if no_ridership > station_count * 0.3:
            issues.append({
                "severity": SEVERITY_LOW,
                "category": "駅データ (S12)",
                "message": f"乗降客数欠損: {no_ridership}/{station_count}駅",
                "detail": "乗降客数が0の駅は流量スコアに寄与しません。",
            })

    # ---------------------------------------------------------------
    # 3. DPF facility categories
    # ---------------------------------------------------------------
    dpf_categories = {
        "welfare": ("福祉施設 (P14)", SEVERITY_MEDIUM),
        "medical": ("医療施設 (P04)", SEVERITY_MEDIUM),
        "public": ("公共施設 (P02)", SEVERITY_MEDIUM),
    }

    for cat, (label, severity) in dpf_categories.items():
        items = facilities.get(cat, [])
        count = len(items)
        if count == 0:
            issues.append({
                "severity": SEVERITY_HIGH,
                "category": label,
                "message": f"{label}が0件です",
                "detail": "DPF APIの応答を確認してください。bbox範囲が狭い可能性があります。",
            })
            coverage_scores[cat] = 0
        elif count < MIN_FACILITIES_PER_CATEGORY:
            issues.append({
                "severity": severity,
                "category": label,
                "message": f"{label}が少数: {count}件（推奨: {MIN_FACILITIES_PER_CATEGORY}件以上）",
                "detail": "施設ミックススコアの精度が低下する可能性があります。",
            })
            coverage_scores[cat] = round(count / MIN_FACILITIES_PER_CATEGORY * 100, 1)
        else:
            coverage_scores[cat] = 100.0

    # ---------------------------------------------------------------
    # 4. Overpass commercial data
    # ---------------------------------------------------------------
    commercial = facilities.get("commercial", [])
    commercial_count = len(commercial)
    if commercial_count == 0:
        issues.append({
            "severity": SEVERITY_HIGH,
            "category": "商業データ (Overpass)",
            "message": "商業施設データが0件です",
            "detail": f"Overpass APIのarea名 \"{config.get('overpass_area', '')}\" が正確か確認してください。"
                      "漢字の揺れや未登録の自治体名で0件になることがあります。",
        })
        coverage_scores["commercial"] = 0
    elif commercial_count < MIN_COMMERCIAL:
        issues.append({
            "severity": SEVERITY_MEDIUM,
            "category": "商業データ (Overpass)",
            "message": f"商業データが少数: {commercial_count}件（推奨: {MIN_COMMERCIAL}件以上）",
            "detail": "にぎわい創出型の判定精度が低下します。OSMマッピングが疎らなエリアの可能性があります。",
        })
        coverage_scores["commercial"] = round(commercial_count / MIN_COMMERCIAL * 100, 1)
    else:
        coverage_scores["commercial"] = 100.0

    # Check other overpass categories
    for osm_cat in ["childcare_osm", "education", "elderly_osm"]:
        items = facilities.get(osm_cat, [])
        if len(items) == 0:
            issues.append({
                "severity": SEVERITY_LOW,
                "category": f"OSMデータ ({osm_cat})",
                "message": f"{osm_cat}のOSMデータが0件",
                "detail": "DPFデータで補完されますが、カバレッジに偏りがある可能性があります。",
            })

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    high_count = sum(1 for i in issues if i["severity"] == SEVERITY_HIGH)
    medium_count = sum(1 for i in issues if i["severity"] == SEVERITY_MEDIUM)

    if high_count > 0:
        summary = "FAIL"
    elif medium_count > 0:
        summary = "WARN"
    else:
        summary = "PASS"

    overall_score = round(
        sum(coverage_scores.values()) / max(len(coverage_scores), 1), 1
    )

    return {
        "municipality": municipality,
        "issues": issues,
        "coverage_scores": coverage_scores,
        "overall_score": overall_score,
        "summary": summary,
        "counts": {
            "parks": total_parks,
            "stations": station_count,
            "welfare": len(facilities.get("welfare", [])),
            "medical": len(facilities.get("medical", [])),
            "public": len(facilities.get("public", [])),
            "commercial": commercial_count,
        },
    }
