from __future__ import annotations

import json
import os
import sys

import requests


API_VERSION = os.getenv("INSTAGRAM_API_VERSION", "v26.0").strip()
GRAPH_BASE = os.getenv("INSTAGRAM_GRAPH_BASE", "https://graph.facebook.com").rstrip("/")


def main() -> int:
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not token:
        print("INSTAGRAM_ACCESS_TOKEN is missing", file=sys.stderr)
        return 2

    url = f"{GRAPH_BASE}/{API_VERSION}/me/accounts"
    response = requests.get(
        url,
        params={
            "fields": "id,name,instagram_business_account{id,name,username}",
            "access_token": token,
        },
        timeout=30,
    )

    try:
        data = response.json()
    except Exception:
        print(f"HTTP {response.status_code}: non-JSON response", file=sys.stderr)
        return 3

    if not response.ok or data.get("error"):
        print(json.dumps(data, ensure_ascii=False, indent=2), file=sys.stderr)
        return 4

    found = []
    for page in data.get("data", []):
        ig = page.get("instagram_business_account")
        if not isinstance(ig, dict) or not ig.get("id"):
            continue
        found.append({
            "facebook_page_id": page.get("id"),
            "facebook_page_name": page.get("name"),
            "instagram_ig_user_id": ig.get("id"),
            "instagram_username": ig.get("username"),
            "instagram_name": ig.get("name"),
        })

    if not found:
        print("No Instagram Business account connected to any accessible Facebook Page.")
        return 5

    print(json.dumps(found, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
