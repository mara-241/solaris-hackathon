#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request

from tasklib import find_task, load_tasks

REQUIRED = ["ci", "goldenPath", "eoFallback", "codexReview", "geminiReview", "pushAuthorized"]


def is_ready(task: dict) -> tuple[bool, list[str]]:
    checks = task.get("checks", {})
    missing = [k for k in REQUIRED if checks.get(k) != "pass"]
    return (len(missing) == 0, missing)


def send_telegram(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read().decode("utf-8")
    payload = json.loads(body)
    if not payload.get("ok"):
        raise RuntimeError(f"telegram send failed: {payload}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--pr", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    doc = load_tasks()
    task = find_task(doc, args.id)
    if not task:
        raise SystemExit(f"task not found: {args.id}")

    ready, missing = is_ready(task)
    if not ready:
        raise SystemExit(f"task not review-ready. missing checks: {', '.join(missing)}")

    pr = args.pr or task.get("pr") or "(no PR link yet)"
    msg = (
        f"✅ Review Ready\n"
        f"Task: {task.get('id')}\n"
        f"Title: {task.get('title')}\n"
        f"Branch: {task.get('branch')}\n"
        f"PR: {pr}\n"
        f"Checks: ci/goldenPath/eoFallback/codex/gemini/pushAuthorized = pass"
    )

    if args.dry_run:
        print(msg)
        return 0

    send_telegram(msg)
    print("telegram ping sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
