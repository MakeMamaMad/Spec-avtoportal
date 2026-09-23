from .normalize import norm_text


def should_exclude(item: dict, exclude_rules: dict) -> bool:
    """Return True when an item contains a configured editorial exclusion.

    Rules are treated as normalized substrings rather than whole words so that
    Russian inflections such as "зерновозы" also match the configured
    "зерновоз" keyword.
    """
    text = norm_text((item.get("title") or "") + " " + (item.get("summary") or "")).casefold()
    for keyword in exclude_rules.get("keywords", []):
        needle = norm_text(str(keyword)).casefold()
        if needle and needle in text:
            return True
    return False
