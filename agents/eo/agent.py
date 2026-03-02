def extract_eo_features(request: dict) -> dict:
    # TODO: Sentinel-2 + NDVI/NDWI + cloud scoring + VLM interpretation
    return {
        "ndvi_mean": 0.41,
        "ndwi_mean": 0.08,
        "cloud_score": 0.72,
        "eo_quality": 0.72,
        "fallback_used": False,
    }
