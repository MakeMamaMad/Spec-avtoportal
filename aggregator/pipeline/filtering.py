import re
from .normalize import norm_text

def should_exclude(item: dict, exclude_rules: dict) -> bool:
    text = norm_text((item.get('title') or '') + ' ' + (item.get('summary') or ''))
    for kw in exclude_rules.get('keywords', []):
        if re.search(rf'\b{re.escape(kw)}\b', text, flags=re.I):
            return True
    return False
