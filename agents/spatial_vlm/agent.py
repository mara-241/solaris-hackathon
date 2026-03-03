def analyze_spatial_context(request: dict) -> dict:
    # TODO: integrate Imagery Adapter + Compression SDK + VLM router
    return {
        "status": "ok",
        "confidence": 0.74,
        "assumptions": [
            "Imagery-derived proxies are used when direct infrastructure mapping is unavailable."
        ],
        "quality_flags": [],
        "imagery": {"provider": "gee", "compressed": True},
        "feature_summaries": {
            "ndvi_mean": 0.41,
            "roof_count_estimate": 112,
            "settlement_density": "medium",
        },
        "visual_embeddings_ref": "s3://artifacts/mock/embedding.bin",
        "fallback_used": False,
    }
