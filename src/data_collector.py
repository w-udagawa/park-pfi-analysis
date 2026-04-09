"""Data collection: GeoJSON parsing, MLIT DPF GraphQL, Overpass API with JSON caching."""

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from .config_loader import load_config
from .geo_utils import bounding_box_with_buffer, get_centroid

TYPE_NAMES = {
    1: "街区公園", 2: "近隣公園", 3: "地区公園", 4: "総合公園",
    5: "運動公園", 9: "特殊公園", 11: "都市緑地", 12: "緑道",
    13: "都市林", 14: "広場公園",
}

# 目的地型商業施設 — にぎわい分析で有効なshopタグ
DESTINATION_SHOP_TYPES = {
    # ファッション・小売
    "clothes", "shoes", "bag", "jewelry", "fashion_accessories", "watches", "cosmetics",
    # 食品専門店（日本の商店街で集客力のある店舗）
    "bakery", "pastry", "confectionery", "deli", "coffee", "tea",
    "chocolate", "cheese", "alcohol", "beverages", "greengrocer",
    "butcher", "seafood", "health_food", "organic",
    # 書籍・文化・エンタメ
    "books", "music", "musical_instrument", "art", "craft",
    "photo", "camera", "video", "video_games",
    # ホーム・ライフスタイル
    "furniture", "interior_decoration", "kitchen", "houseware",
    "garden_centre", "florist",
    # スポーツ・アウトドア
    "sports", "outdoor", "bicycle",
    # 雑貨・ギフト・専門
    "gift", "toys", "pet", "stationery", "antiques", "second_hand",
    # 家電（日本では秋葉原文化含め目的地）
    "electronics", "computer", "mobile_phone",
    # 大型商業
    "variety_store", "department_store", "mall",
    # 旅行
    "travel_agency",
}

DESTINATION_AMENITY_TYPES = {"restaurant", "cafe", "bar"}
# fast_food は除外: マクドナルド等はにぎわい指標としては弱い


def _is_destination_commercial(tags: dict) -> bool:
    """Check if an OSM element is a destination-type commercial facility."""
    shop = tags.get("shop", "")
    amenity = tags.get("amenity", "")
    if shop in DESTINATION_SHOP_TYPES:
        return True
    if amenity in DESTINATION_AMENITY_TYPES:
        return True
    return False


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(config: dict, key: str) -> str:
    cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), config["cache"]["directory"])
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{key}.json")


def _cache_get(config: dict, key: str) -> Optional[Any]:
    path = _cache_path(config, key)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        cached = json.load(f)
    ts = datetime.fromisoformat(cached["timestamp"])
    ttl = cached.get("ttl_hours", config["cache"]["ttl_hours"])
    age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    if age_hours > ttl:
        return None
    return cached["data"]


def _cache_set(config: dict, key: str, data: Any) -> None:
    path = _cache_path(config, key)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ttl_hours": config["cache"]["ttl_hours"],
        "data": data,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _bbox_hash(top: float, bottom: float, left: float, right: float) -> str:
    s = f"{top:.4f}_{bottom:.4f}_{left:.4f}_{right:.4f}"
    return hashlib.md5(s.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# GeoJSON parks loader
# ---------------------------------------------------------------------------

def load_parks(config: dict) -> List[Dict[str, Any]]:
    """Load parks from GeoJSON, filter by municipality and min area."""
    geojson_path = config["geojson_path"]
    filter_field = config["municipality"]["filter_field"]
    filter_value = config["municipality"]["filter_value"]
    min_area = config["min_area"]

    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    parks = []
    for feat in data["features"]:
        props = feat["properties"]
        if props.get(filter_field) != filter_value:
            continue
        area = props.get("供用済面積", 0) or 0
        if area < min_area:
            continue

        lat, lon = get_centroid(feat["geometry"])
        if lat is None:
            continue

        parks.append({
            "name": props.get("公園名", "不明"),
            "type_code": props.get("公園種別", 0),
            "type_name": TYPE_NAMES.get(props.get("公園種別", 0), "不明"),
            "area_m2": area,
            "year_opened": props.get("供用開始年"),
            "lat": lat,
            "lon": lon,
            "address_pref": props.get("所在地都道府県名", ""),
            "address_city": props.get("所在地市区町村名", ""),
        })

    parks.sort(key=lambda p: -p["area_m2"])
    return parks


def get_parks_bbox(parks: List[Dict]) -> Tuple[float, float, float, float]:
    """Get bounding box of all parks. Returns (top_lat, bottom_lat, left_lon, right_lon)."""
    lats = [p["lat"] for p in parks]
    lons = [p["lon"] for p in parks]
    return max(lats), min(lats), min(lons), max(lons)


# ---------------------------------------------------------------------------
# MLIT DPF GraphQL client
# ---------------------------------------------------------------------------

def _build_search_query(
    dataset_id: str,
    top_lat: float, bottom_lat: float, left_lon: float, right_lon: float,
    first: int = 0, size: int = 500,
) -> str:
    """Build GraphQL search query with rectangle location filter."""
    top = max(top_lat, bottom_lat)
    bottom = min(top_lat, bottom_lat)
    left = min(left_lon, right_lon)
    right = max(left_lon, right_lon)

    location_filter = (
        f"{{rectangle: {{topLeft: {{lat: {top}, lon: {left}}}, "
        f"bottomRight: {{lat: {bottom}, lon: {right}}}}}}}"
    )
    attribute_filter = f'{{attributeName: "DPF:dataset_id", is: "{dataset_id}"}}'

    return f"""
    query {{
      search(
        term: "",
        attributeFilter: {attribute_filter},
        locationFilter: {location_filter},
        first: {first},
        size: {size}
      ) {{
        totalNumber
        searchResults {{
          id
          title
          lat
          lon
          year
          metadata
          dataset_id
        }}
      }}
    }}
    """.strip()


def _build_get_all_data_query(
    dataset_id: str,
    top_lat: float, bottom_lat: float, left_lon: float, right_lon: float,
    size: int = 500,
    next_token: Optional[str] = None,
) -> str:
    """Build GraphQL getAllData query for paginated bulk retrieval."""
    top = max(top_lat, bottom_lat)
    bottom = min(top_lat, bottom_lat)
    left = min(left_lon, right_lon)
    right = max(left_lon, right_lon)

    location_filter = (
        f"{{rectangle: {{topLeft: {{lat: {top}, lon: {left}}}, "
        f"bottomRight: {{lat: {bottom}, lon: {right}}}}}}}"
    )
    attribute_filter = f'{{attributeName: "DPF:dataset_id", is: "{dataset_id}"}}'

    token_part = f', nextDataRequestToken: "{next_token}"' if next_token else ""

    return f"""
    query {{
      getAllData(
        attributeFilter: {attribute_filter},
        locationFilter: {location_filter},
        size: {size}{token_part}
      ) {{
        totalNumber
        nextDataRequestToken
        getAllDataResults {{
          id
          title
          lat
          lon
          year
          metadata
          dataset_id
        }}
      }}
    }}
    """.strip()


def _dpf_request(config: dict, query: str) -> dict:
    """Execute a GraphQL request against MLIT DPF API."""
    endpoint = config["dpf"]["endpoint"]
    api_key = config["dpf"].get("api_key", "")

    resp = requests.post(
        endpoint,
        json={"query": query},
        headers={
            "Content-Type": "application/json",
            "apikey": api_key,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _get_metadata(metadata, key: str) -> Optional[str]:
    """Extract a value from DPF metadata dict. Metadata is a flat dict with string keys."""
    if not metadata or not isinstance(metadata, dict):
        return None
    val = metadata.get(key)
    if val is not None:
        return str(val)
    return None


def _extract_station_data(result: dict) -> Dict[str, Any]:
    """Extract station info from a DPF search result."""
    meta = result.get("metadata", {})
    # Get latest ridership (joukou_kyakusuu) - try most recent years first
    ridership = 0
    for year in range(2023, 2010, -1):
        val = _get_metadata(meta, f"NLNI:joukou_kyakusuu_{year}")
        if val:
            try:
                ridership = int(float(val))
                break
            except (ValueError, TypeError):
                continue

    station_name = _get_metadata(meta, "NLNI:eki_mei") or result.get("title", "不明")
    line_name = _get_metadata(meta, "NLNI:rosen_mei") or ""
    operator = _get_metadata(meta, "NLNI:unei_kaisha") or ""

    return {
        "id": result.get("id", ""),
        "name": station_name,
        "line": line_name,
        "operator": operator,
        "lat": result.get("lat"),
        "lon": result.get("lon"),
        "ridership": ridership,
        "year": result.get("year"),
    }


def _extract_facility_data(result: dict, category: str) -> Dict[str, Any]:
    """Extract facility info from a DPF search result."""
    meta = result.get("metadata", {})
    # P14 welfare: major category code (05=childcare, 99=other/elderly, etc.)
    major_code = _get_metadata(meta, "NLNI:P14_005") if category == "welfare" else None
    sub_code = _get_metadata(meta, "NLNI:P14_006") if category == "welfare" else None
    facility_name = _get_metadata(meta, "NLNI:P14_008") or result.get("title", "不明")

    return {
        "id": result.get("id", ""),
        "name": facility_name,
        "lat": result.get("lat"),
        "lon": result.get("lon"),
        "category": category,
        "major_code": major_code,
        "sub_code": sub_code,
        "year": result.get("year"),
    }


# ---------------------------------------------------------------------------
# Bulk data fetchers
# ---------------------------------------------------------------------------

def fetch_stations(config: dict, parks: List[Dict]) -> List[Dict[str, Any]]:
    """Fetch all railway stations within bounding box + buffer. Uses cache."""
    bbox = get_parks_bbox(parks)
    buffer_m = config["flow"]["buffer_meters"]
    expanded = bounding_box_with_buffer(*bbox, buffer_m)
    municipality = config["municipality"]["name"]
    cache_key = f"dpf_stations_{municipality}_{_bbox_hash(*expanded)}"

    cached = _cache_get(config, cache_key)
    if cached is not None:
        print(f"  [cache hit] stations: {len(cached)} records")
        return cached

    dataset_id = config["dpf"]["datasets"]["stations"]
    page_size = config["dpf"]["page_size"]
    top, bottom, left, right = expanded

    # First, use search to get total count
    query = _build_search_query(dataset_id, top, bottom, left, right, first=0, size=page_size)
    resp = _dpf_request(config, query)

    search_data = resp.get("data", {}).get("search", {})
    total = search_data.get("totalNumber", 0)
    results = search_data.get("searchResults", [])
    print(f"  [API] stations: {total} total, got {len(results)} in first page")

    # Paginate if needed
    offset = len(results)
    while offset < total:
        query = _build_search_query(dataset_id, top, bottom, left, right, first=offset, size=page_size)
        resp = _dpf_request(config, query)
        page_results = resp.get("data", {}).get("search", {}).get("searchResults", [])
        if not page_results:
            break
        results.extend(page_results)
        offset += len(page_results)
        print(f"  [API] stations: fetched {len(results)}/{total}")

    stations = [_extract_station_data(r) for r in results]
    # Filter out stations with no coordinates
    stations = [s for s in stations if s["lat"] is not None and s["lon"] is not None]
    # Merge duplicate station entries (same station split across multiple lines).
    # DPF data stores one record per line, and ridership may be missing on
    # some line records. Group by (name, operator) and take max ridership,
    # aggregating line names.
    stations = _merge_station_lines(stations)
    _cache_set(config, cache_key, stations)
    return stations


def _merge_station_lines(stations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge station records that represent the same physical station.

    Same (name, operator) = same station. Takes max ridership, concatenates
    line names, and uses coordinates of the record with max ridership.
    """
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for s in stations:
        key = (s["name"], s.get("operator", ""))
        groups.setdefault(key, []).append(s)

    merged: List[Dict[str, Any]] = []
    for (name, operator), recs in groups.items():
        # Pick representative: entry with highest ridership
        best = max(recs, key=lambda r: r.get("ridership", 0) or 0)
        lines = sorted({r.get("line", "") for r in recs if r.get("line")})
        merged.append({
            "id": best.get("id", ""),
            "name": name,
            "line": " / ".join(lines),
            "operator": operator,
            "lat": best["lat"],
            "lon": best["lon"],
            "ridership": max((r.get("ridership", 0) or 0) for r in recs),
            "year": best.get("year"),
        })
    return merged


def fetch_facilities(config: dict, parks: List[Dict], category: str) -> List[Dict[str, Any]]:
    """Fetch facilities of a given category within bounding box + buffer. Uses cache."""
    bbox = get_parks_bbox(parks)
    buffer_m = config["facility"]["buffer_meters"]
    expanded = bounding_box_with_buffer(*bbox, buffer_m)
    municipality = config["municipality"]["name"]
    cache_key = f"dpf_{category}_{municipality}_{_bbox_hash(*expanded)}"

    cached = _cache_get(config, cache_key)
    if cached is not None:
        print(f"  [cache hit] {category}: {len(cached)} records")
        return cached

    dataset_id = config["dpf"]["datasets"].get(category)
    if not dataset_id:
        print(f"  [skip] No dataset ID for category: {category}")
        return []

    page_size = config["dpf"]["page_size"]
    top, bottom, left, right = expanded

    query = _build_search_query(dataset_id, top, bottom, left, right, first=0, size=page_size)
    resp = _dpf_request(config, query)

    search_data = resp.get("data", {}).get("search", {})
    total = search_data.get("totalNumber", 0)
    results = search_data.get("searchResults", [])
    print(f"  [API] {category}: {total} total, got {len(results)} in first page")

    offset = len(results)
    while offset < total:
        query = _build_search_query(dataset_id, top, bottom, left, right, first=offset, size=page_size)
        resp = _dpf_request(config, query)
        page_results = resp.get("data", {}).get("search", {}).get("searchResults", [])
        if not page_results:
            break
        results.extend(page_results)
        offset += len(page_results)
        print(f"  [API] {category}: fetched {len(results)}/{total}")

    facilities = [_extract_facility_data(r, category) for r in results]
    facilities = [f for f in facilities if f["lat"] is not None and f["lon"] is not None]
    _cache_set(config, cache_key, facilities)
    return facilities


def fetch_overpass_data(config: dict) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch commercial and other OSM data via Overpass API for the municipality area.

    Returns dict with keys: 'commercial', 'childcare', 'elderly', etc.
    """
    area_name = config.get("overpass_area", config["municipality"]["filter_value"])
    cache_key = f"overpass_v2_{area_name.replace(' ', '_')}"

    cached = _cache_get(config, cache_key)
    if cached is not None:
        total = sum(len(v) for v in cached.values())
        print(f"  [cache hit] overpass: {total} records")
        return cached

    # Query for shops, amenities relevant to PFI analysis
    query = f"""
    [out:json][timeout:{config['overpass']['timeout']}];
    area["name"="{area_name}"]->.a;
    (
      // Commercial / retail
      node["shop"](area.a);
      way["shop"](area.a);
      node["amenity"="restaurant"](area.a);
      node["amenity"="cafe"](area.a);
      node["amenity"="fast_food"](area.a);
      node["amenity"="bar"](area.a);
      // Childcare
      node["amenity"="kindergarten"](area.a);
      way["amenity"="kindergarten"](area.a);
      node["amenity"="childcare"](area.a);
      way["amenity"="childcare"](area.a);
      // Education
      node["amenity"="school"](area.a);
      way["amenity"="school"](area.a);
      // Elderly care
      node["amenity"="social_facility"]["social_facility"="nursing_home"](area.a);
      way["amenity"="social_facility"]["social_facility"="nursing_home"](area.a);
      node["amenity"="social_facility"]["social_facility"="group_home"](area.a);
      way["amenity"="social_facility"]["social_facility"="group_home"](area.a);
    );
    out center;
    """.strip()

    # Try multiple Overpass endpoints with retries (公開エンドポイントは混雑しがち)
    fallback_endpoints = [
        config["overpass"]["endpoint"],
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://overpass.openstreetmap.fr/api/interpreter",
    ]
    # 重複除去(順序維持)
    seen = set()
    endpoints = [e for e in fallback_endpoints if not (e in seen or seen.add(e))]

    timeout_sec = config["overpass"]["timeout"] + 30
    elements = None
    last_error = None
    for endpoint in endpoints:
        for attempt in range(2):
            try:
                print(f"  [API] overpass POST {endpoint} (attempt {attempt + 1})")
                resp = requests.post(endpoint, data={"data": query}, timeout=timeout_sec)
                resp.raise_for_status()
                elements = resp.json().get("elements", [])
                print(f"  [API] overpass: {len(elements)} elements")
                break
            except (requests.HTTPError, requests.ConnectionError, requests.Timeout, ValueError) as e:
                last_error = e
                status = getattr(getattr(e, "response", None), "status_code", None)
                print(f"  [warn] overpass {endpoint} failed: {type(e).__name__} {status or ''}")
                # 504/429/503なら同じエンドポイントで1回リトライ。それ以外は次のエンドポイントへ
                if status not in (429, 503, 504):
                    break
        if elements is not None:
            break

    if elements is None:
        raise RuntimeError(
            f"Overpass API: 全エンドポイントが失敗しました。最後のエラー: {last_error}"
        )

    # Classify elements
    result: Dict[str, List[Dict]] = {
        "commercial": [],
        "childcare": [],
        "education": [],
        "elderly": [],
    }

    for el in elements:
        tags = el.get("tags", {})
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue

        item = {
            "name": tags.get("name", ""),
            "lat": lat,
            "lon": lon,
            "tags": tags,
        }

        amenity = tags.get("amenity", "")
        shop = tags.get("shop", "")

        if shop or amenity in ("restaurant", "cafe", "fast_food", "bar"):
            if _is_destination_commercial(tags):
                result["commercial"].append(item)
        elif amenity in ("kindergarten", "childcare"):
            result["childcare"].append(item)
        elif amenity == "school":
            result["education"].append(item)
        elif amenity == "social_facility":
            result["elderly"].append(item)

    # フィルタログ出力
    total_raw_commercial = sum(
        1 for el in elements
        if el.get("tags", {}).get("shop") or el.get("tags", {}).get("amenity") in ("restaurant", "cafe", "fast_food", "bar")
    )
    excluded = total_raw_commercial - len(result["commercial"])
    print(f"  [filter] commercial: {len(result['commercial'])} destination / {excluded} excluded")

    _cache_set(config, cache_key, result)
    return result


def collect_all_data(config: dict) -> Dict[str, Any]:
    """Main data collection entry point. Returns all data needed for analysis."""
    print("Loading parks from GeoJSON...")
    parks = load_parks(config)
    print(f"  Found {len(parks)} parks (>= {config['min_area']}m²)")

    print("Fetching station data from MLIT DPF...")
    stations = fetch_stations(config, parks)
    print(f"  Total stations: {len(stations)}")

    print("Fetching facility data from MLIT DPF...")
    facility_categories = ["welfare", "public", "medical"]
    facilities = {}
    for cat in facility_categories:
        facilities[cat] = fetch_facilities(config, parks, cat)

    print("Fetching Overpass data (commercial, childcare, education, elderly)...")
    overpass = fetch_overpass_data(config)
    # Merge overpass data into facilities
    facilities["commercial"] = overpass.get("commercial", [])
    facilities["childcare_osm"] = overpass.get("childcare", [])
    facilities["education"] = overpass.get("education", [])
    facilities["elderly_osm"] = overpass.get("elderly", [])

    return {
        "parks": parks,
        "stations": stations,
        "facilities": facilities,
    }
