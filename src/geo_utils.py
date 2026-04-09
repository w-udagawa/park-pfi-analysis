"""Geographic utility functions: Haversine distance, centroid extraction, spatial filtering."""

import math
from typing import Optional, Tuple, List, Dict, Any


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters between two lat/lon points."""
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_centroid(geometry: dict) -> Tuple[Optional[float], Optional[float]]:
    """Extract centroid (lat, lon) from a GeoJSON geometry."""
    gtype = geometry.get("type", "")
    coords = geometry.get("coordinates", [])

    if gtype == "Point":
        return coords[1], coords[0]
    elif gtype == "MultiPoint":
        lats = [c[1] for c in coords]
        lons = [c[0] for c in coords]
        return sum(lats) / len(lats), sum(lons) / len(lons)
    elif gtype == "Polygon":
        ring = coords[0]
        lats = [c[1] for c in ring]
        lons = [c[0] for c in ring]
        return sum(lats) / len(lats), sum(lons) / len(lons)
    elif gtype == "MultiPolygon":
        all_lats, all_lons = [], []
        for poly in coords:
            ring = poly[0]
            all_lats.extend([c[1] for c in ring])
            all_lons.extend([c[0] for c in ring])
        return sum(all_lats) / len(all_lats), sum(all_lons) / len(all_lons)

    return None, None


def points_within_radius(
    center_lat: float,
    center_lon: float,
    points: List[Dict[str, Any]],
    radius_m: float,
    lat_key: str = "lat",
    lon_key: str = "lon",
) -> List[Tuple[Dict[str, Any], float]]:
    """Return points within radius_m of center, with distances.

    Returns list of (point_dict, distance_meters) sorted by distance.
    """
    results = []
    for pt in points:
        lat = pt.get(lat_key)
        lon = pt.get(lon_key)
        if lat is None or lon is None:
            continue
        dist = haversine(center_lat, center_lon, lat, lon)
        if dist <= radius_m:
            results.append((pt, dist))
    results.sort(key=lambda x: x[1])
    return results


def bounding_box_with_buffer(
    top_lat: float, bottom_lat: float, left_lon: float, right_lon: float, buffer_m: float
) -> Tuple[float, float, float, float]:
    """Expand a bounding box by buffer_m meters. Returns (top, bottom, left, right)."""
    # Approximate: 1 degree lat ≈ 111,000m, 1 degree lon ≈ 91,000m at 35.6°N
    lat_offset = buffer_m / 111000
    lon_offset = buffer_m / 91000
    return (
        top_lat + lat_offset,
        bottom_lat - lat_offset,
        left_lon - lon_offset,
        right_lon + lon_offset,
    )
