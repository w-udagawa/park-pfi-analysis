"""Pedestrian flow scoring based on station ridership with distance decay."""

import math
from typing import Any, Dict, List, Tuple

from .geo_utils import points_within_radius


def calculate_flow_score(
    park: Dict[str, Any],
    stations: List[Dict[str, Any]],
    max_radius: float = 800,
    decay_constant: float = 400,
) -> Dict[str, Any]:
    """Calculate raw flow score for a single park.

    flow_score = Σ (ridership × exp(-distance / decay_constant))
    for all stations within max_radius.
    """
    nearby = points_within_radius(
        park["lat"], park["lon"], stations, max_radius
    )

    raw_score = 0.0
    station_details = []
    for station, dist in nearby:
        ridership = station.get("ridership", 0)
        contribution = ridership * math.exp(-dist / decay_constant)
        raw_score += contribution
        station_details.append({
            "name": station["name"],
            "distance_m": round(dist),
            "ridership": ridership,
            "contribution": round(contribution, 1),
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
    max_radius = config["flow"]["max_radius"]
    decay_constant = config["flow"]["decay_constant"]

    # Calculate raw scores
    results = {}
    for park in parks:
        flow_data = calculate_flow_score(park, stations, max_radius, decay_constant)
        results[park["name"]] = flow_data

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
