"""Webapp helpers: prefecture/municipality selection, bbox computation, config builder."""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .config_loader import deep_merge

# 都道府県 → GeoJSONファイル名のマッピング
PREFECTURE_GEOJSON = {
    "東京都": "tokyo_parks.geojson",
    "神奈川県": "kanagawa_parks.geojson",
    "埼玉県": "saitama_parks.geojson",
    "千葉県": "chiba_parks.geojson",
}


def available_prefectures(geojson_dir: Path) -> List[str]:
    """data/geojson/ 配下に存在するファイルに対応する都道府県のみ返す。"""
    available = []
    for pref, filename in PREFECTURE_GEOJSON.items():
        if (geojson_dir / filename).exists():
            available.append(pref)
    return available


def geojson_path_for(prefecture: str, geojson_dir: Path) -> Path:
    """都道府県名から GeoJSON ファイルパスを取得する。"""
    filename = PREFECTURE_GEOJSON.get(prefecture)
    if not filename:
        raise ValueError(f"Unknown prefecture: {prefecture}")
    return geojson_dir / filename


def load_municipalities(prefecture: str, geojson_dir: Path) -> List[str]:
    """指定都道府県の GeoJSON から 所在地市区町村名 のユニーク値を抽出して返す。

    「所在地市区町村名」を使うことで、都道府県管理の公園（管理市区町村が空白）も
    正しくその所在地の自治体に含まれる。
    """
    path = geojson_path_for(prefecture, geojson_dir)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    municipalities = set()
    for feature in data.get("features", []):
        name = feature.get("properties", {}).get("所在地市区町村名")
        if name and name.strip():
            municipalities.add(name)
    return sorted(municipalities)


def compute_bbox(
    geojson_path: Path,
    municipality: str,
    filter_field: str = "所在地市区町村名",
    margin_deg: float = 0.01,
    min_area_m2: float = 0,
) -> Dict[str, float]:
    """指定自治体の公園座標から bbox (top/bottom/left/right) を算出する。

    margin_deg: bbox 4辺に追加するマージン（駅・周辺施設の取りこぼし防止）
    """
    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    lats, lons = [], []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        if props.get(filter_field) != municipality:
            continue

        area = props.get("供用済面積", 0) or 0
        if area < min_area_m2:
            continue

        geom = feature.get("geometry", {})
        coords = geom.get("coordinates")
        if not coords:
            continue

        gtype = geom.get("type", "")
        if gtype == "Point":
            lons.append(coords[0])
            lats.append(coords[1])
        elif gtype in ("MultiPoint", "LineString"):
            for c in coords:
                lons.append(c[0])
                lats.append(c[1])
        elif gtype == "Polygon":
            for c in coords[0]:
                lons.append(c[0])
                lats.append(c[1])
        elif gtype == "MultiPolygon":
            for poly in coords:
                for c in poly[0]:
                    lons.append(c[0])
                    lats.append(c[1])

    if not lats or not lons:
        raise ValueError(
            f"{municipality} の公園座標が見つかりません（面積 {min_area_m2}m² 以上）"
        )

    return {
        "top_lat": max(lats) + margin_deg,
        "bottom_lat": min(lats) - margin_deg,
        "left_lon": min(lons) - margin_deg,
        "right_lon": max(lons) + margin_deg,
    }


def build_config_dict(
    prefecture: str,
    municipality: str,
    geojson_dir: Path,
    default_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Web から受け取った自治体情報をもとに、分析に使える config dict を組み立てる。"""
    geojson_path = geojson_path_for(prefecture, geojson_dir).resolve()
    min_area = default_config.get("min_area", 960)
    bbox = compute_bbox(geojson_path, municipality, min_area_m2=min_area)

    override = {
        "municipality": {
            "name": municipality,
            "filter_field": "所在地市区町村名",
            "filter_value": municipality,
        },
        "geojson_path": str(geojson_path),
        "bbox": bbox,
        "overpass_area": municipality,
    }
    return deep_merge(default_config, override)
