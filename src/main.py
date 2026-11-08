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
from .realphotos import RealPhotos
from .script_gen import make_script
from .video import build_video, make_thumbnail

DISCLAIMER = ("This video is for entertainment and educational purposes only and is not financial, legal or tax "
              "advice. Narration uses an AI voice. Photos are real and credited above; some visuals are AI-generated "
              "illustrations, not footage of the events. Facts are taken from the sources listed above.")


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


def describe(s, intro, chapters=None, link_note=None, credits=None):
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
    if credits:
        out.append("Photo & footage credits (licenses as stated):\n"
                   + "\n".join(f"- {c}" for c in credits[:25]))
    out.append(DISCLAIMER)
    text = "\n\n".join(out)
    if len(text) > 4900:   # keep the disclaimer: trim credits/references first
        text = text[:4900 - len(DISCLAIMER) - 8].rsplit("\n", 1)[0] + "\n...\n\n" + DISCLAIMER
    return text


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
    # no documentary today and Shorts/Reels from the last one are still queued -> just post today's Reels
    if not do_long and not a.short_only and queued:
        print(f"[main] {ch['name']} | no documentary today; {len(queued)} Reel(s) in the Instagram queue")
        if not a.dry_run:
            post_queued_reel(ch, cfg, queue_dir)
        return
    # one YouTube Short per day: the series has exactly as many parts as days until the next documentary
    days = days_until_next_doc(today, ch["long_days"])
    ch.setdefault("long", {})["short_parts"] = max(2, min(5, days))
    print(f"[main] {ch['name']} | documentary today: {do_long}"
          + (f" | {ch['long']['short_parts']}-part Shorts series" if do_long else ""))

    s = make_script(ch, history, cfg["llm"], long_form=do_long, max_ai_long=cfg["video"]["ai_images_long"])
    work = Path("output") / a.channel / today.strftime("%Y%m%d")
    work.mkdir(parents=True, exist_ok=True)
    (work / "script.json").write_text(json.dumps(
        {k: v for k, v in s.items() if k not in ("source_text", "_photos_txt")}, indent=1))
    stock = Stock("cache", ch["fallback_visuals"])
    img = ImageGen("cache/ai", ch["visual_style"], cfg["images"])
    photos = RealPhotos()
    ppool = s.get("photo_pool") or []
    fx = cfg["video"].get("sound_effects", False)
    tags = s.get("tags", [])
    hour = int(cfg["youtube"].get("shorts_hour_utc", 17))

    def credits_for(paths):
        c = [photos.credits[p] for p in dict.fromkeys(map(str, paths)) if p in photos.credits]
        return c + [f"Stock footage: {x}" for x in sorted(stock.sources_used)]

    def at_day(k):
        when = (today + dt.timedelta(days=k)).replace(hour=hour, minute=0, second=0, microsecond=0)
        return max(when, today + dt.timedelta(hours=2))

    videos = []   # (kind, path, title, description, thumb, publish_at, caption, ig_day or None)
    if do_long:
        info = {}
        long_path = build_video(s["scenes"], ch, stock, img, work / "long", False, cfg["video"], "long.mp4",
                                cast=s.get("cast"), effects=fx, info=info, photos=photos, photo_pool=ppool)
        all_imgs = [p for k in sorted(info["scene_images"]) for p in info["scene_images"][k]]
        bg = next((p for p in all_imgs if not p.endswith(".mp4")), None)
        try:
            img.budget = img.count + 1
            img.klein_used = 0   # thumbnail is worth one premium image
            bg = img.generate(s.get("thumbnail_prompt", s["title"]), False)
        except Exception as e:  # noqa: BLE001
            print(f"[thumb] AI failed ({str(e)[:80]}), using the documentary's first image")
        thumb = make_thumbnail(bg, s["thumbnail_text"], work / "thumb.jpg", tuple(ch["accent"]))
        videos.append(("long", long_path, s["title"],
                       describe(s, s["description"], info["chapters"], credits=credits_for(all_imgs)),
                       thumb, None, None, None))
        parts = s.get("parts") or []
        for k, p in enumerate(parts):   # YouTube: Part k goes public on day k; Instagram: same day
            pool = [x for c in p["chapters"] for x in info["scene_images"].get(c - 1, [])] or all_imgs
            path = build_video(p["beats"], ch, stock, img, work / f"part{k + 1}", True, cfg["video"],
                               f"part{k + 1}.mp4", title=p["title"], cast=s.get("cast"), effects=fx,
                               image_pool=pool)
            cap = f"{p.get('caption', '')}\n\n" + " ".join("#" + h.lstrip("#") for h in p.get("hashtags", []))
            videos.append((f"part{k + 1}", path, p["title"] + " #shorts",
                           describe(s, p.get("caption") or s["description"], link_note="Full documentary on the channel.",
                                    credits=credits_for(pool)), None, at_day(k), cap, k))
        # Instagram extra: chapter clips (no new images, free) spread over the same days
        n_clips = int(cfg["instagram"].get("clips_per_doc", 6))
        ndays = max(1, len(parts))
        tagline = " ".join("#" + t.replace(" ", "") for t in tags[:6])
        chosen = [i for i in range(len(s["scenes"]))][:: max(1, len(s["scenes"]) // max(n_clips, 1))][:n_clips]
        for j, ci in enumerate(chosen):
            sc = s["scenes"][ci]
            beats, words = [], 0
            for b in sc["beats"]:
                if words > 140:
                    break
                beats.append({**b, "shot": {"type": "image"} if b["shot"]["type"] != "stat" else b["shot"]})
                words += len(b["text"].split())
            pool = info["scene_images"].get(ci, []) or all_imgs
            title = sc.get("title") or s["title"]
            path = build_video(beats, ch, stock, img, work / f"clip{j + 1}", True, cfg["video"], f"clip{j + 1}.mp4",
                               title=title, cast=s.get("cast"), effects=fx, image_pool=pool)
            cap = f"{title} - from our documentary \"{s['title']}\". Full story on YouTube.\n\n{tagline}"
            videos.append((f"clip{j + 1}", path, title, "", None, None, cap, j % ndays))
    else:
        sh = s["short"]
        sinfo = {}
        path = build_video(sh["beats"], ch, stock, img, work / "short", True, cfg["video"], "short.mp4",
                           title=sh.get("title"), cast=s.get("cast"), effects=fx, info=sinfo,
                           photos=photos, photo_pool=ppool)
        used = [p for ps in sinfo.get("scene_images", {}).values() for p in ps]
        cap = f"{sh.get('caption', '')}\n\n" + " ".join("#" + h.lstrip("#") for h in sh.get("hashtags", []))
        videos.append(("short", path, sh["title"] + " #shorts",
                       describe(s, sh.get("caption") or s["description"], credits=credits_for(used)),
                       None, None, cap, 0))
    print("[main] built:\n  " + "\n  ".join(f"{k}: {p}" for k, p, *_ in videos))
    (work / "uploads.json").write_text(json.dumps(
        [{"kind": k, "file": str(p), "title": t, "description": d, "youtube_publish_at": str(w),
          "instagram_day": g, "caption": c} for k, p, t, d, _, w, c, g in videos], indent=1))

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
        for kind, path, title, desc, thumb, when, _, _ in videos:
            if kind.startswith("clip"):
                continue   # chapter clips are Instagram-only
            entry[f"yt_{kind}"] = upload(yt, path, title, desc, tags, privacy, yc["category_id"], thumb, when)
            ok += 1
    except Exception as e:  # noqa: BLE001
        print(f"[yt] FAILED: {e}")

    # Instagram has no scheduling: queue every Reel with the day it should go out, post today's now
    if verified:
        for kind, path, title, desc, thumb, when, cap, day in videos:
            if day is None:
                continue
            post_on = (today + dt.timedelta(days=day)).strftime("%Y-%m-%d")
            stem = f"{post_on}_{today:%H%M}_{kind}"
            shutil.copy(path, queue_dir / f"{stem}.mp4")
            (queue_dir / f"{stem}.json").write_text(json.dumps({"file": f"{stem}.mp4", "caption": cap,
                                                                "post_on": post_on}))
        ok += post_queued_reel(ch, cfg, queue_dir)
    history.append(entry)
    hist_path.parent.mkdir(exist_ok=True)
    hist_path.write_text(json.dumps(hist_all, indent=1))
    if ok == 0:
        sys.exit("All uploads failed")


def days_until_next_doc(today, long_days):
    for k in range(1, 8):
        if (today + dt.timedelta(days=k)).strftime("%a") in long_days:
            return k
    return 7


def post_queued_reel(ch, cfg, queue_dir):
    """Posts up to instagram.posts_per_day Reels that are due (Part of the day first, then clips)."""
    n, limit = 0, int(cfg["instagram"].get("posts_per_day", 3))
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    for _ in range(limit):
        due = [p for p in sorted(queue_dir.glob("*.json"))
               if json.loads(p.read_text()).get("post_on", "0000") <= today]
        due.sort(key=lambda p: (p.name.split("_")[0], "_part" not in p.name, p.name))
        if not due:
            break
        n += _post_one(ch, cfg, queue_dir, due[0])
    return n


def _post_one(ch, cfg, queue_dir, item):
    items = [item]
    meta = json.loads(item.read_text())
    video = queue_dir / meta["file"]
    try:
        from .upload_instagram import upload_reel
        sec = ch["secrets"]
        upload_reel(os.environ[sec["ig_user"]], os.environ[sec["ig_token"]], video, meta["caption"],
                    cfg["instagram"]["graph_version"])
        items[0].unlink(); video.unlink(missing_ok=True)
        print(f"[ig] posted {meta['file']} ({len(list(queue_dir.glob('*.json')))} left in queue)")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"[ig] FAILED (stays queued for tomorrow): {e}")
        return 0


if __name__ == "__main__":
    main()
