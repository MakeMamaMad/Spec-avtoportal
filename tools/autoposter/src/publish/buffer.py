from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import requests


API_URL = "https://api.buffer.com"


class BufferAPIError(RuntimeError):
    pass


def _graphql(api_key: str, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    if not api_key.strip():
        raise BufferAPIError("BUFFER_API_KEY is required")

    response = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"query": query, "variables": variables or {}},
        timeout=45,
    )
    try:
        payload = response.json()
    except Exception as exc:
        raise BufferAPIError(
            f"Buffer API HTTP {response.status_code}: invalid JSON"
        ) from exc

    if not response.ok:
        raise BufferAPIError(f"Buffer API HTTP {response.status_code}: {payload}")
    if payload.get("errors"):
        raise BufferAPIError(f"Buffer GraphQL error: {payload['errors']}")
    return payload.get("data") or {}


def list_channels(api_key: str) -> list[dict[str, Any]]:
    account_query = """
    query AccountOrganizations {
      account {
        organizations {
          id
        }
      }
    }
    """
    data = _graphql(api_key, account_query)
    organizations = ((data.get("account") or {}).get("organizations") or [])
    channels: list[dict[str, Any]] = []

    channel_query = """
    query GetChannels($organizationId: OrganizationId!) {
      channels(input: { organizationId: $organizationId }) {
        id
        name
        displayName
        service
        isQueuePaused
      }
    }
    """
    for org in organizations:
        org_id = str((org or {}).get("id") or "").strip()
        if not org_id:
            continue
        org_data = _graphql(api_key, channel_query, {"organizationId": org_id})
        for channel in org_data.get("channels") or []:
            if isinstance(channel, dict):
                channels.append({"organizationId": org_id, **channel})
    return channels


def discover_tiktok_channel(api_key: str, preferred_name: str = "") -> dict[str, Any]:
    channels = list_channels(api_key)
    tiktok = [
        channel
        for channel in channels
        if str(channel.get("service") or "").lower() == "tiktok"
    ]
    if not tiktok:
        raise BufferAPIError("No TikTok channel is connected to this Buffer account")

    preferred = preferred_name.strip().lower()
    if preferred:
        for channel in tiktok:
            names = {
                str(channel.get("name") or "").strip().lower(),
                str(channel.get("displayName") or "").strip().lower(),
            }
            if preferred in names:
                return channel

    if len(tiktok) == 1:
        return tiktok[0]

    summary = [
        {
            "id": x.get("id"),
            "name": x.get("name"),
            "displayName": x.get("displayName"),
        }
        for x in tiktok
    ]
    raise BufferAPIError(
        f"Multiple TikTok channels found; set BUFFER_TIKTOK_CHANNEL_NAME. Candidates: {summary}"
    )


def create_video_post(
    *,
    api_key: str,
    channel_id: str,
    video_url: str,
    text: str,
    scheduling_type: str = "notification",
    mode: str = "shareNow",
    thumbnail_offset_ms: int = 1000,
) -> dict[str, Any]:
    mutation = """
    mutation CreateVideoPost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess {
          post {
            id
            text
            dueAt
            status
            schedulingType
            shareMode
          }
        }
        ... on MutationError {
          message
        }
      }
    }
    """
    variables = {
        "input": {
            "text": text,
            "channelId": channel_id,
            "schedulingType": scheduling_type,
            "mode": mode,
            "assets": [
                {
                    "video": {
                        "url": video_url,
                        "metadata": {"thumbnailOffset": thumbnail_offset_ms},
                    }
                }
            ],
        }
    }
    data = _graphql(api_key, mutation, variables)
    result = data.get("createPost") or {}
    if result.get("message") and not result.get("post"):
        raise BufferAPIError(str(result["message"]))
    post = result.get("post")
    if not isinstance(post, dict) or not post.get("id"):
        raise BufferAPIError(f"Unexpected Buffer createPost response: {result}")
    return post


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-url")
    parser.add_argument("--text-file")
    parser.add_argument("--share-now", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("BUFFER_API_KEY", "").strip()
    preferred_name = os.getenv("BUFFER_TIKTOK_CHANNEL_NAME", "specavtoportal")
    channel = discover_tiktok_channel(api_key, preferred_name)
    print(
        "[buffer] TikTok connected:",
        f"id={channel.get('id')}",
        f"name={channel.get('name')}",
        f"displayName={channel.get('displayName')}",
        f"paused={channel.get('isQueuePaused')}",
    )

    if args.video_url:
        text = ""
        if args.text_file:
            text = Path(args.text_file).read_text(encoding="utf-8").strip()
        post = create_video_post(
            api_key=api_key,
            channel_id=str(channel["id"]),
            video_url=args.video_url,
            text=text,
            scheduling_type="notification",
            mode="shareNow" if args.share_now else "addToQueue",
        )
        print(
            "[buffer] post created:",
            f"id={post.get('id')}",
            f"status={post.get('status')}",
            f"schedulingType={post.get('schedulingType')}",
            f"shareMode={post.get('shareMode')}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
