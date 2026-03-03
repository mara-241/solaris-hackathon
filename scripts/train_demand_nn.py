#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def generate_row() -> tuple[list[float], float]:
    rain = random.uniform(0.0, 0.9)
    sun = random.uniform(2.0, 8.0)
    households = random.uniform(40.0, 300.0)
    usage = random.choice(["mixed", "productive-use-heavy", "residential"])
    roof = households * random.uniform(0.7, 1.3)
    ndvi = random.uniform(0.1, 0.8)
    density = random.choice(["low", "medium", "high", "unknown"])

    usage_vec = [1.0 if usage == c else 0.0 for c in ["mixed", "productive-use-heavy", "residential"]]
    density_vec = [1.0 if density == c else 0.0 for c in ["low", "medium", "high", "unknown"]]

    x = [rain, sun, households, *usage_vec, roof, ndvi, *density_vec]

    # synthetic target generator
    y = (
        households * 1.25
        + max(0.0, (5.5 - sun)) * 8.0
        + rain * 22.0
        + (10.0 if usage == "productive-use-heavy" else 0.0)
        + (6.0 if density == "high" else 0.0)
        + random.uniform(-4.0, 4.0)
    )
    return x, max(1.0, y)


def stats(cols: list[list[float]]) -> tuple[list[float], list[float]]:
    mean = [sum(c) / len(c) for c in cols]
    std = []
    for i, c in enumerate(cols):
        m = mean[i]
        v = sum((x - m) ** 2 for x in c) / len(c)
        std.append(max(1e-6, v ** 0.5))
    return mean, std


def normalize(X: list[list[float]], mean: list[float], std: list[float]) -> list[list[float]]:
    return [[(v - m) / s for v, m, s in zip(row, mean, std)] for row in X]


def relu(v: list[float]) -> list[float]:
    return [max(0.0, x) for x in v]


def drelu(v: list[float]) -> list[float]:
    return [1.0 if x > 0 else 0.0 for x in v]


def matvec(W: list[list[float]], x: list[float], b: list[float]) -> list[float]:
    return [sum(wi * xi for wi, xi in zip(row, x)) + bi for row, bi in zip(W, b)]


def init_layer(out_dim: int, in_dim: int, scale: float = 0.05):
    W = [[random.uniform(-scale, scale) for _ in range(in_dim)] for _ in range(out_dim)]
    b = [0.0 for _ in range(out_dim)]
    return W, b


def train(X: list[list[float]], y: list[float], epochs: int = 200, lr: float = 0.002):
    in_dim = len(X[0])
    W1, b1 = init_layer(4, in_dim)
    W2, b2 = init_layer(3, 4)
    W3, b3 = init_layer(1, 3)

    n = len(X)
    for _ in range(epochs):
        for i in range(n):
            x = X[i]
            target = y[i]

            z1 = matvec(W1, x, b1)
            a1 = relu(z1)
            z2 = matvec(W2, a1, b2)
            a2 = relu(z2)
            pred = matvec(W3, a2, b3)[0]

            dloss = 2.0 * (pred - target)

            # layer 3 grads
            gW3 = [[dloss * a2[j] for j in range(3)]]
            gb3 = [dloss]

            da2 = [dloss * W3[0][j] for j in range(3)]
            dz2 = [da2[j] * drelu([z2[j]])[0] for j in range(3)]

            gW2 = [[dz2[r] * a1[c] for c in range(4)] for r in range(3)]
            gb2 = dz2[:]

            da1 = [sum(dz2[r] * W2[r][c] for r in range(3)) for c in range(4)]
            dz1 = [da1[j] * drelu([z1[j]])[0] for j in range(4)]

            gW1 = [[dz1[r] * x[c] for c in range(in_dim)] for r in range(4)]
            gb1 = dz1[:]

            # SGD step
            for r in range(4):
                for c in range(in_dim):
                    W1[r][c] -= lr * gW1[r][c]
                b1[r] -= lr * gb1[r]
            for r in range(3):
                for c in range(4):
                    W2[r][c] -= lr * gW2[r][c]
                b2[r] -= lr * gb2[r]
            for c in range(3):
                W3[0][c] -= lr * gW3[0][c]
            b3[0] -= lr * gb3[0]

    return {
        "layers": [
            {"weights": W1, "bias": b1},
            {"weights": W2, "bias": b2},
            {"weights": W3, "bias": b3},
        ]
    }


def predict(model: dict, x: list[float]) -> float:
    z1 = matvec(model["layers"][0]["weights"], x, model["layers"][0]["bias"])
    a1 = relu(z1)
    z2 = matvec(model["layers"][1]["weights"], a1, model["layers"][1]["bias"])
    a2 = relu(z2)
    y = matvec(model["layers"][2]["weights"], a2, model["layers"][2]["bias"])[0]
    return max(0.0, y)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=500)
    ap.add_argument("--epochs", type=int, default=160)
    ap.add_argument("--out", default="docs/models/demand_nn_v1.weights.json")
    ap.add_argument("--metrics", default="docs/models/demand_nn_v1.metrics.json")
    args = ap.parse_args()

    random.seed(7)
    rows = [generate_row() for _ in range(args.samples)]
    X = [r[0] for r in rows]
    y = [r[1] for r in rows]

    cols = [[row[i] for row in X] for i in range(len(X[0]))]
    mean, std = stats(cols)
    Xn = normalize(X, mean, std)

    model = train(Xn, y, epochs=args.epochs)

    preds = [predict(model, x) for x in Xn]
    mae = sum(abs(p - t) for p, t in zip(preds, y)) / len(y)
    rmse = (sum((p - t) ** 2 for p, t in zip(preds, y)) / len(y)) ** 0.5

    payload = {
        "model_name": "demand_nn_v1_tiny_mlp",
        "model_input_version": "v1",
        "normalization": {"mean": mean, "std": std},
        "layers": model["layers"],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))

    m = {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "samples": args.samples,
        "epochs": args.epochs,
    }
    Path(args.metrics).write_text(json.dumps(m, indent=2))
    print(json.dumps({"ok": True, "weights": str(out_path), "metrics": m}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
