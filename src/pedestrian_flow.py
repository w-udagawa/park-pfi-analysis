"""Pedestrian flow scoring: simple sum of ridership for stations within radius."""

from typing import Any, Dict, List

from .geo_utils import points_within_radius


def calculate_flow_score(
    park: Dict[str, Any],
    stations: List[Dict[str, Any]],
    radius_m: float = 500,
) -> Dict[str, Any]:
    """半径 radius_m 以内の駅乗降客数を単純合計する。

    raw_score = Σ ridership   for all stations within radius_m
    """
    nearby = points_within_radius(park["lat"], park["lon"], stations, radius_m)

    raw_score = 0.0
    station_details = []
    for station, dist in nearby:
        ridership = station.get("ridership", 0) or 0
        raw_score += ridership
        station_details.append({
            "name": station["name"],
            "distance_m": round(dist),
            "ridership": ridership,
        })

    nearest_station = station_details[0] if station_details else None

    return {
        "raw_score": round(raw_score, 1),
        "station_count": len(station_details),
        "nearest_station": nearest_station,
        "station_details": station_details,
    }


def calculate_all_flow_scores(
    parks: List[Dict[str, Any]],
    stations: List[Dict[str, Any]],
    config: dict,
) -> Dict[str, Dict[str, Any]]:
    """Calculate flow scores for all parks with percentile normalization.

    Returns dict keyed by park name with flow data + normalized score (0-100).
    """
    radius_m = config["flow"]["max_radius"]

    # Calculate raw scores
    results = {}
    for park in parks:
        results[park["name"]] = calculate_flow_score(park, stations, radius_m)

    # Percentile normalization (rank-based 0-100)
    raw_scores = [(name, data["raw_score"]) for name, data in results.items()]
    raw_scores.sort(key=lambda x: x[1])

    n = len(raw_scores)
    for rank, (name, _) in enumerate(raw_scores):
        if n <= 1:
            percentile = 50.0
        else:
            percentile = round(rank / (n - 1) * 100, 1)
        results[name]["normalized_score"] = percentile

    return results
