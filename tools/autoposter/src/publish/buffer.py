from __future__ import annotations

import time
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
        timeout=60,
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
    data = _graphql(
        api_key,
        """
        query AccountOrganizations {
          account { organizations { id } }
        }
        """,
    )
    organizations = ((data.get("account") or {}).get("organizations") or [])
    channels: list[dict[str, Any]] = []

    query = """
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
        org_data = _graphql(api_key, query, {"organizationId": org_id})
        for channel in org_data.get("channels") or []:
            if isinstance(channel, dict):
                channels.append({"organizationId": org_id, **channel})
    return channels


def discover_channel(api_key: str, service: str, preferred_name: str = "") -> dict[str, Any]:
    wanted_service = service.strip().lower()
    matches = [
        channel
        for channel in list_channels(api_key)
        if str(channel.get("service") or "").strip().lower() == wanted_service
    ]
    if not matches:
        raise BufferAPIError(f"No {service} channel is connected to this Buffer account")

    preferred = preferred_name.strip().lower()
    if preferred:
        for channel in matches:
            names = {
                str(channel.get("name") or "").strip().lower(),
                str(channel.get("displayName") or "").strip().lower(),
            }
            if preferred in names:
                return channel

    if len(matches) == 1:
        return matches[0]

    summary = [
        {"id": x.get("id"), "name": x.get("name"), "displayName": x.get("displayName")}
        for x in matches
    ]
    raise BufferAPIError(
        f"Multiple {service} channels found; configure the preferred channel name. Candidates: {summary}"
    )


def create_video_post(
    *,
    api_key: str,
    service: str,
    channel_id: str,
    video_url: str,
    text: str,
    scheduling_type: str = "automatic",
    mode: str = "shareNow",
    thumbnail_offset_ms: int = 1000,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    service_name = service.strip().lower()
    if service_name == "tiktok":
        metadata["tiktok"] = {"isAiGenerated": True}
    elif service_name == "instagram":
        metadata["instagram"] = {
            "type": "reel",
            "shouldShareToFeed": True,
            "isAiGenerated": True,
        }

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
            "metadata": metadata,
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


def fetch_post(api_key: str, post_id: str) -> dict[str, Any]:
    data = _graphql(
        api_key,
        """
        query GetPost($id: PostId!) {
          post(input: {id: $id}) {
            id
            status
            schedulingType
            shareMode
            notificationStatus
            error {
              message
              rawError
              supportUrl
            }
          }
        }
        """,
        {"id": post_id},
    )
    post = data.get("post")
    if not isinstance(post, dict):
        raise BufferAPIError(f"Buffer post not found: {post_id}")
    return post


def publish_video(
    *,
    api_key: str,
    service: str,
    preferred_name: str,
    video_url: str,
    text: str,
    wait_seconds: int = 120,
) -> dict[str, Any]:
    channel = discover_channel(api_key, service, preferred_name)
    post = create_video_post(
        api_key=api_key,
        service=service,
        channel_id=str(channel["id"]),
        video_url=video_url,
        text=text,
        scheduling_type="automatic",
        mode="shareNow",
    )
    post_id = str(post["id"])
    print(
        f"[buffer] {service}: submitted post_id={post_id} "
        f"channel={channel.get('displayName') or channel.get('name')} status={post.get('status')}"
    )

    deadline = time.monotonic() + max(0, wait_seconds)
    latest = post
    while time.monotonic() < deadline:
        time.sleep(5)
        latest = fetch_post(api_key, post_id)
        status = str(latest.get("status") or "").strip().lower()
        error = latest.get("error")
        print(f"[buffer] {service}: post_id={post_id} status={status}")
        if error or status == "error":
            detail = error or {"message": "Buffer post failed"}
            raise BufferAPIError(f"{service} Buffer post failed: {detail}")
        if status in {"sent", "published", "success", "completed"}:
            return {
                "platform": service,
                "status": "published",
                "provider": "buffer",
                "post_id": post_id,
                "buffer_status": status,
            }

    status = str(latest.get("status") or post.get("status") or "").strip().lower()
    if status == "error" or latest.get("error"):
        raise BufferAPIError(f"{service} Buffer post failed: {latest.get('error')}")
    return {
        "platform": service,
        "status": "submitted",
        "provider": "buffer",
        "post_id": post_id,
        "buffer_status": status or "submitted",
    }
