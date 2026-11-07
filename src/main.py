"""Entry point.
  python -m src.main --channel cash_and_court              daily run (long day: documentary + Shorts series)
  python -m src.main --channel cash_and_court --force-long  make a documentary today
  python -m src.main --channel cash_and_court --short-only  one standalone Short (quick test)
  --dry-run  build everything, upload nothing"""
import argparse, datetime as dt, json, os, shutil, sys
from pathlib import Path
import yaml

from .footage import Stock
from .imagegen import ImageGen
from .script_gen import make_script
from .video import build_video, make_thumbnail

DISCLAIMER = ("This video is for entertainment and educational purposes only and is not financial, legal or tax "
              "advice. Narration uses an AI voice; visuals are AI-generated illustrations, not real footage of the "
              "events. Facts are taken from the sources listed above.")


def _load_env():
    if Path(".env").exists():  # local runs: KEY=VALUE lines
        for line in Path(".env").read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip().strip('"'))


def _ts(sec):
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02}:{sec % 60:02}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02}"


def describe(s, intro, chapters=None, link_note=None):
    """Description = hook + chapters + every source (Wikipedia article + the references it cites) + disclaimer."""
    out = [intro.strip()]
    if link_note:
        out.append(link_note)
    if chapters and len(chapters) >= 3:
        ch = [(t if i else "Intro", max(0, round(st))) for i, (t, st) in enumerate(chapters)]
        ch[0] = (ch[0][0], 0)
        out.append("Chapters:\n" + "\n".join(f"{_ts(st)} {t}" for t, st in ch))
    src = [f"Main source: {s.get('source_title', '')} (Wikipedia) {s.get('source_url', '')}"]
    refs = s.get("references") or []
    if refs:
        src.append("Original reporting and records cited by that article:")
        src += [f"- {u}" for u in refs]
    out.append("SOURCES & PROOF\n" + "\n".join(src))
    out.append(DISCLAIMER)
    return "\n\n".join(out)[:4900]


def main():
    _load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True)
    ap.add_argument("--force-long", action="store_true")
    ap.add_argument("--short-only", action="store_true", help="one standalone Short (fast test)")
    ap.add_argument("--dry-run", action="store_true", help="build videos, skip uploads")
    a = ap.parse_args()

    cfg = yaml.safe_load(open("config.yaml"))
    ch = cfg["channels"][a.channel]
    yc = cfg["youtube"]
    hist_path = Path("data/history.json")
    hist_all = json.loads(hist_path.read_text() or "{}") if hist_path.exists() else {}
    history = hist_all.setdefault(a.channel, [])
    queue_dir = Path("queue") / a.channel
    queue_dir.mkdir(parents=True, exist_ok=True)
    queued = sorted(queue_dir.glob("*.json"))

    today = dt.datetime.now(dt.timezone.utc)
    is_long_day = today.strftime("%a") in ch["long_days"]
    do_long = not a.short_only and (a.force_long or is_long_day)
    # no documentary today and Reels still queued from the last one -> just post the next queued Reel
    if not do_long and not a.short_only and queued:
        print(f"[main] {ch['name']} | no documentary today; {len(queued)} queued Reel(s)")
        if not a.dry_run:
            post_queued_reel(ch, cfg, queue_dir)
        return
    print(f"[main] {ch['name']} | documentary today: {do_long}")

    s = make_script(ch, history, cfg["llm"], long_form=do_long, max_ai_long=cfg["video"]["ai_images_long"])
    work = Path("output") / a.channel / today.strftime("%Y%m%d")
    work.mkdir(parents=True, exist_ok=True)
    (work / "script.json").write_text(json.dumps({k: v for k, v in s.items() if k != "source_text"}, indent=1))
    stock = Stock("cache", ch["fallback_visuals"])
    img = ImageGen("cache/ai", ch["visual_style"], cfg["images"])
    fx = cfg["video"].get("sound_effects", False)
    tags = s.get("tags", [])

    videos = []   # (kind, path, title, description, thumb, publish_at, caption)
    if do_long:
        info = {}
        long_path = build_video(s["scenes"], ch, stock, img, work / "long", False, cfg["video"], "long.mp4",
                                cast=s.get("cast"), effects=fx, info=info)
        try:
            img.budget = img.count + 1
            bg = img.generate(s.get("thumbnail_prompt", s["title"]), False)
        except Exception as e:  # noqa: BLE001
            print(f"[thumb] AI failed: {e}")
            bg = next((p for ps in info["scene_images"].values() for p in ps), None)
        thumb = make_thumbnail(bg, s["thumbnail_text"], work / "thumb.jpg", tuple(ch["accent"]))
        videos.append(("long", long_path, s["title"], describe(s, s["description"], info["chapters"]),
                       thumb, None, None))
        all_imgs = [p for k in sorted(info["scene_images"]) for p in info["scene_images"][k]]
        parts = s.get("parts") or []
        hour = int(cfg["youtube"].get("shorts_hour_utc", 17))
        for k, p in enumerate(parts):
            pool = [x for c in p["chapters"] for x in info["scene_images"].get(c - 1, [])] or all_imgs
            path = build_video(p["beats"], ch, stock, img, work / f"part{k + 1}", True, cfg["video"],
                               f"part{k + 1}.mp4", title=p["title"], cast=s.get("cast"), effects=fx,
                               image_pool=pool)
            when = (today + dt.timedelta(days=k)).replace(hour=hour, minute=0, second=0, microsecond=0)
            if when <= today + dt.timedelta(minutes=30):
                when = today + dt.timedelta(hours=2)
            cap = f"{p.get('caption', '')}\n\n" + " ".join("#" + h.lstrip("#") for h in p.get("hashtags", []))
            videos.append((f"part{k + 1}", path, p["title"] + " #shorts",
                           describe(s, p.get("caption") or s["description"],
                                    link_note="Full documentary on the channel."), None, when, cap))
    else:
        sh = s["short"]
        path = build_video(sh["beats"], ch, stock, img, work / "short", True, cfg["video"], "short.mp4",
                           title=sh.get("title"), cast=s.get("cast"), effects=fx)
        cap = f"{sh.get('caption', '')}\n\n" + " ".join("#" + h.lstrip("#") for h in sh.get("hashtags", []))
        videos.append(("short", path, sh["title"] + " #shorts", describe(s, sh.get("caption") or s["description"]),
                       None, None, cap))
    print("[main] built:\n  " + "\n  ".join(f"{k}: {p}" for k, p, *_ in videos))
    (work / "uploads.json").write_text(json.dumps(
        [{"kind": k, "file": str(p), "title": t, "description": d, "publish_at": str(w), "caption": c}
         for k, p, t, d, _, w, c in videos], indent=1))

    entry = {"date": today.strftime("%Y-%m-%d"), "title": s["title"], "pillar": s.get("pillar"),
             "source_title": s.get("source_title"), "factcheck": s.get("factcheck")}
    if a.dry_run:
        print(f"[main] dry run: descriptions and schedule in {work / 'uploads.json'}")
        return

    fc = s.get("factcheck", {})
    verified = bool(fc) and all(isinstance(v, dict) and v.get("method") in ("google-search", "source-grounded")
                                for v in fc.values())
    privacy = yc["privacy"] if verified else "private"
    if not verified:
        print("[main] facts NOT verified -> YouTube private, Instagram skipped. Review it.")
    sec, ok = ch["secrets"], 0
    try:
        from .upload_youtube import service, upload
        yt = service(os.environ[sec["yt_token"]])
        for kind, path, title, desc, thumb, when, _ in videos:
            entry[f"yt_{kind}"] = upload(yt, path, title, desc, tags, privacy, yc["category_id"], thumb, when)
            ok += 1
    except Exception as e:  # noqa: BLE001
        print(f"[yt] FAILED: {e}")

    # Instagram has no scheduling: queue every Reel, post one per day (the first one now)
    if verified:
        for kind, path, title, desc, thumb, when, cap in videos:
            if kind == "long":
                continue
            dst = queue_dir / f"{today:%Y%m%d}_{kind}.mp4"
            shutil.copy(path, dst)
            (queue_dir / f"{today:%Y%m%d}_{kind}.json").write_text(json.dumps({"file": dst.name, "caption": cap}))
        ok += post_queued_reel(ch, cfg, queue_dir)
    history.append(entry)
    hist_path.parent.mkdir(exist_ok=True)
    hist_path.write_text(json.dumps(hist_all, indent=1))
    if ok == 0:
        sys.exit("All uploads failed")


def post_queued_reel(ch, cfg, queue_dir):
    """Posts the oldest queued Reel (two if the queue is building up)."""
    n = 0
    for _ in range(2 if len(list(queue_dir.glob("*.json"))) > 4 else 1):
        n += _post_one(ch, cfg, queue_dir)
    return n


def _post_one(ch, cfg, queue_dir):
    items = sorted(queue_dir.glob("*.json"))
    if not items:
        return 0
    meta = json.loads(items[0].read_text())
    video = queue_dir / meta["file"]
    try:
        from .upload_instagram import upload_reel
        sec = ch["secrets"]
        upload_reel(os.environ[sec["ig_user"]], os.environ[sec["ig_token"]], video, meta["caption"],
                    cfg["instagram"]["graph_version"])
        items[0].unlink(); video.unlink(missing_ok=True)
        print(f"[ig] posted {meta['file']} ({len(items) - 1} left in queue)")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"[ig] FAILED (stays queued for tomorrow): {e}")
        return 0


if __name__ == "__main__":
    main()
