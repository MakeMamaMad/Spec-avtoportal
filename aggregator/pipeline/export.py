import json
from pathlib import Path
from typing import List, Dict, Union

def export_json(items: List[Dict], path: Union[str, Path]):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"items": items}
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
