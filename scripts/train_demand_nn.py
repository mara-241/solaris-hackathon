#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import random
from pathlib import Path

MODEL_PATH = Path("docs/models/demand_nn_v1.weights.json")
METRICS_PATH = Path("docs/models/demand_nn_v1.metrics.json")


def synth_target(rain_risk: float, sun_hours: float, households: float, ndvi: float) -> float:
    # Synthetic pseudo-ground truth for hackathon training/demo.
    return max(30.0, 0.95 * households * (1.0 + 0.2 * rain_risk) * (5.5 / max(2.5, sun_hours)) * (1.0 - 0.1 * ndvi))


def predict(weights: dict, x: list[float]) -> float:
    # Keep training lightweight: calibrate output bias only for stability.
    # This uses a simple linearized projection to tune final bias.
    mean = weights["normalization"]["mean"]
    std = weights["normalization"]["std"]
    xn = [(v - m) / (s if s else 1.0) for v, m, s in zip(x, mean, std)]

    def dense(inp, layer):
        out = []
        for row, b in zip(layer["weights"], layer["bias"]):
            out.append(sum(i * w for i, w in zip(inp, row)) + b)
        return out

    l1 = [max(0.0, v) for v in dense(xn, weights["layers"][0])]
    l2 = [max(0.0, v) for v in dense(l1, weights["layers"][1])]
    y = dense(l2, weights["layers"][2])[0]
    return max(0.0, y)


def build_sample() -> tuple[list[float], float]:
    rain = random.uniform(0.1, 0.8)
    sun = random.uniform(3.0, 8.0)
    hh = random.uniform(60, 260)
    usage = random.choice([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    roof = hh * random.uniform(0.7, 1.3)
    ndvi = random.uniform(0.15, 0.7)
    density = random.choice([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
    x = [rain, sun, hh, *usage, roof, ndvi, *density]
    y = synth_target(rain, sun, hh, ndvi)
    return x, y


def main() -> int:
    random.seed(42)
    weights = json.loads(MODEL_PATH.read_text())

    # Tiny calibration: adjust final bias via gradient steps on synthetic data.
    lr = 0.0008
    for _ in range(250):
        x, y = build_sample()
        yhat = predict(weights, x)
        err = yhat - y
        weights["layers"][2]["bias"][0] -= lr * err

    # Evaluate metrics
    errs = []
    for _ in range(200):
        x, y = build_sample()
        yhat = predict(weights, x)
        errs.append(yhat - y)

    mae = sum(abs(e) for e in errs) / len(errs)
    rmse = math.sqrt(sum(e * e for e in errs) / len(errs))

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(weights, indent=2) + "\n")

    metrics = {
        "model_name": weights.get("model_name", "demand_nn_v1_tiny_mlp"),
        "samples_eval": len(errs),
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "dataset": "synthetic_v1",
    }
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps({"ok": True, **metrics}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
