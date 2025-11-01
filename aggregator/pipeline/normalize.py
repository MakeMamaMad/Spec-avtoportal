import re, html
def norm_text(s:str)->str:
    s = s or ""
    s = html.unescape(s)
    s = re.sub(r'\s+', ' ', s, flags=re.M).strip()
    return s

def to_tags(text:str)->list[str]:
    base = []
    t = text.lower()
    for k in ["цистерн","рама","подвеск","крепёж","рынок","дилер","двигател","тягач","экспо","выставк"]:
        if k in t: base.append(k)
    return base
