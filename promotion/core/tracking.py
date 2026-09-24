from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def build_tracking_url(
    destination: str,
    *,
    source: str,
    medium: str,
    campaign: str,
    content: str,
) -> str:
    """Return destination with deterministic UTM parameters.

    Existing query parameters are preserved; UTM keys managed by this helper
    replace older values with the same names.
    """
    parts = urlsplit(destination)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(
        {
            "utm_source": source,
            "utm_medium": medium,
            "utm_campaign": campaign,
            "utm_content": content,
        }
    )
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )
