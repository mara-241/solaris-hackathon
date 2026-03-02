#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class NodeResult:
    node_id: str
    sample_count: int
    local_loss: float
    weights: list[float]


def fedavg(nodes: list[NodeResult]) -> list[float]:
    total = sum(n.sample_count for n in nodes)
    dim = len(nodes[0].weights)
    out = [0.0] * dim
    for i in range(dim):
        out[i] = sum(n.weights[i] * n.sample_count for n in nodes) / total
    return out


def main() -> int:
    # Simulated local training results (stub for Flock.io integration).
    local = [
        NodeResult("ngo-node-a", 120, 0.42, [0.51, -0.22, 0.18]),
        NodeResult("ngo-node-b", 85, 0.47, [0.49, -0.18, 0.21]),
        NodeResult("ngo-node-c", 140, 0.39, [0.53, -0.2, 0.17]),
    ]

    global_weights = fedavg(local)
    weighted_loss = sum(n.local_loss * n.sample_count for n in local) / sum(n.sample_count for n in local)

    report = {
        "ok": True,
        "mode": "federated_demo_stub",
        "round": 1,
        "participants": [
            {"node_id": n.node_id, "sample_count": n.sample_count, "local_loss": n.local_loss}
            for n in local
        ],
        "aggregation": {
            "algorithm": "FedAvg",
            "weighted_by": "sample_count",
            "global_weights": [round(v, 6) for v in global_weights],
            "global_loss_estimate": round(weighted_loss, 6),
        },
        "privacy_note": "Raw records remain on each node; only model updates are aggregated.",
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
