from __future__ import annotations


def relu(vec: list[float]) -> list[float]:
    return [max(0.0, v) for v in vec]


def dense(x: list[float], w: list[list[float]], b: list[float]) -> list[float]:
    return [sum(v * rw for v, rw in zip(x, row)) + bias for row, bias in zip(w, b)]


def mlp_forward(x: list[float], model: dict) -> float:
    mu = model["normalization"]["mean"]
    sigma = model["normalization"]["std"]
    xn = [(v - m) / (s if s != 0 else 1.0) for v, m, s in zip(x, mu, sigma)]

    l1 = relu(dense(xn, model["layers"][0]["weights"], model["layers"][0]["bias"]))
    l2 = relu(dense(l1, model["layers"][1]["weights"], model["layers"][1]["bias"]))
    y = dense(l2, model["layers"][2]["weights"], model["layers"][2]["bias"])[0]
    return max(0.0, float(y))
