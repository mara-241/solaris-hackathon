from __future__ import annotations

REQUIRED_CHECKS = [
    "ci",
    "goldenPath",
    "eoFallback",
    "codexReview",
    "geminiReview",
    "pushAuthorized",
]

DEFAULT_CHECKS = {k: "pending" for k in REQUIRED_CHECKS}
