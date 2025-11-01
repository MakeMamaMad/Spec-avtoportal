import re, yaml
from .normalize import norm_text

def build_classifier(rules: dict):
    maps = rules.get('classify', {})
    compiled = {cat: [re.compile(pat, re.I) for pat in pats] for cat, pats in maps.items()}
    def classify(title: str, summary: str) -> str|None:
        text = (title or "") + " " + (summary or "")
        text = norm_text(text)
        for cat, regs in compiled.items():
            if any(r.search(text) for r in regs):
                return cat
        return None
    return classify
