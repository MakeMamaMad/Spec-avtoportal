import datetime
from pathlib import Path

from .config import cfg
from .content.sources import load_items
from .content.digest import build_digest
from .render.video import render_digest_video
from .publish.youtube import upload_video
from .utils.state import load_posted_urls, save_posted_urls

def main():
    items = load_items()
    if not items:
        raise SystemExit(f"No items found. Check CONTENT_JSON_PATH={cfg.CONTENT_JSON_PATH}")

    posted = load_posted_urls()
    picked = []
    for it in items:
        if it.url not in posted:
            picked.append(it)
        if len(picked) >= 3:
            break

    if not picked:
        print("[autoposter] Nothing new to post (all items already posted).")
        return

    plan = build_digest(picked)

    out_dir = Path("out")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    mp4_path = out_dir / f"digest_{ts}.mp4"
    caption_path = out_dir / "caption.txt"

    render_digest_video(plan.slides, mp4_path)
    caption_path.write_text(plan.caption, encoding="utf-8")

    yt_id = upload_video(
        file_path=str(mp4_path),
        title=plan.youtube_title,
        description=plan.youtube_description,
        tags=["прицепы","полуприцепы","грузовики","логистика","госзакупки","инфраструктура"],
        privacy_status=cfg.YOUTUBE_PRIVACY,
    )
    print("[autoposter] YouTube uploaded:", yt_id)

    for it in picked:
        posted.add(it.url)
    save_posted_urls(posted)
    print("[autoposter] State updated. posted_urls:", len(posted))

if __name__ == "__main__":
    main()
