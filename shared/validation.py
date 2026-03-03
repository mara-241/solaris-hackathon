from __future__ import annotations


def parse_lat_lon(payload: dict) -> tuple[float, float, bool]:
    try:
        lat = float(payload.get("lat", 0.0))
        lon = float(payload.get("lon", 0.0))
    except (TypeError, ValueError):
        return 0.0, 0.0, False

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return 0.0, 0.0, False
    return lat, lon, True


def parse_households(value, default: int = 100) -> tuple[int, bool]:
    try:
        h = int(value if value is not None else default)
        if h <= 0:
            raise ValueError
        return h, True
    except (TypeError, ValueError):
        return default, False
