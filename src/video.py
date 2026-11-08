"""Builds the final video beat by beat:
every beat (1-2 sentences) gets its own voice delivery, its own shot that shows what is being said,
and its own sound effect; then a sound bed, word-highlight captions and a cinematic grade are added."""
import math, random, re, subprocess, textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .captions import write_ass
from .sfx import SoundDesign
from .tts import estimate_words, synth_beat

_FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",            # Linux / GitHub
          str(Path.home() / "Library/Fonts/DejaVuSans-Bold.ttf"),            # Mac (brew cask)
          "/Library/Fonts/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
FONT = next((f for f in _FONTS if Path(f).exists()), _FONTS[0])
MOTIONS = ["zoom_in", "pan_right", "zoom_out", "pan_left"]
SCENE_GAP = 0.35  # extra breath between chapters


def _run(cmd, cwd=None):
    p = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"ffmpeg failed: {' '.join(map(str, cmd))[:300]}\n{p.stderr[-1500:]}")


def _duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    return float(out.stdout.strip())


def has_ass():
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return any(line.split()[1:2] == ["ass"] for line in out.splitlines() if line.strip())


def _font(size):
    return ImageFont.truetype(FONT, size)


# ---------- still images ----------------------------------------------------
def _cover(img, W, H):
    img = img.convert("RGB")
    s = max(W / img.width, H / img.height)
    img = img.resize((math.ceil(img.width * s), math.ceil(img.height * s)), Image.LANCZOS)
    l, t = (img.width - W) // 2, (img.height - H) // 2
    return img.crop((l, t, l + W, t + H))


def _title_band(img, title, accent):
    """Shorts header: the hook stays on screen at the top (what makes people stop scrolling)."""
    if not title:
        return img
    d = ImageDraw.Draw(img)
    W = img.width
    for size in range(78, 40, -4):
        f = _font(size)
        lines = textwrap.wrap(title.upper(), width=max(8, int(W * 0.88 / (size * 0.6))))
        if len(lines) <= 3 and all(d.textlength(l, font=f) <= W * 0.9 for l in lines):
            break
    y = 150
    for i, line in enumerate(lines):
        d.text((W / 2, y), line, font=f, anchor="mt", fill=accent if i == 0 else (255, 255, 255),
               stroke_width=6, stroke_fill=(0, 0, 0))
        y += size * 1.15
    return img


def prep_still(src, W, H, out, vertical=False, title=None, accent=(255, 214, 0)):
    """Full-bleed when the image already has the right shape (FLUX.2 makes native 16:9 / 9:16).
    A square image on a Short is framed on a blurred copy of itself instead of being upscaled."""
    im = Image.open(src).convert("RGB")
    img_vertical = im.height > im.width
    if not vertical and im.height > im.width * 1.05:   # portrait photo in a 16:9 video: frame it, don't crop
        bg = ImageEnhance.Brightness(_cover(im, W, H).filter(ImageFilter.GaussianBlur(40))).enhance(0.45)
        s_ = min(H / im.height, W * 0.6 / im.width)
        fg = im.resize((int(im.width * s_), int(im.height * s_)), Image.LANCZOS)
        bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
        bg.save(out, quality=95)
        return out
    if not vertical or img_vertical:
        img = _cover(im, W, H).filter(ImageFilter.UnsharpMask(radius=1.5, percent=50, threshold=2))
        if vertical:  # darken the top a little so the hook title stays readable
            shade = Image.linear_gradient("L").resize((W, H)).point(lambda p: 255 - min(255, int(p * 3.2)))
            img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, shade.point(lambda p: int(p * 0.6)))
    else:
        bg = _cover(im, W, H).filter(ImageFilter.GaussianBlur(40))
        img = ImageEnhance.Brightness(bg).enhance(0.45)
        fg = _cover(im, W, int(W * 1.05)).filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
        img.paste(fg, (0, int(H * 0.22)))
    if vertical:
        img = _title_band(img, title, accent)
    img.save(out, quality=95)
    return out


def stat_card(value, label, W, H, accent, out, bg=None, title=None):
    if bg:
        img = _cover(Image.open(bg), W, H).filter(ImageFilter.GaussianBlur(18))
        img = ImageEnhance.Brightness(img).enhance(0.35)
    else:
        img = Image.new("RGB", (W, H), (12, 12, 16))
        g = ImageDraw.Draw(img)
        for y in range(H):
            k = y / H
            g.line([(0, y), (W, y)], fill=(int(12 + 25 * k), int(12 + 10 * k), int(18 + 20 * k)))
    d = ImageDraw.Draw(img)
    maxw = W * 0.86
    for size in range(int(min(W, H) * 0.30), 40, -6):
        f = _font(size)
        if d.textlength(value, font=f) <= maxw:
            break
    vh = size
    lf = _font(max(34, int(size * 0.28)))
    llines = textwrap.wrap(label.upper(), width=max(10, int(maxw / (lf.size * 0.62))))[:3]
    total = vh + 30 + len(llines) * lf.size * 1.2
    y = (H - total) / 2
    d.text((W / 2, y), value, font=f, fill=accent, anchor="mt", stroke_width=6, stroke_fill=(0, 0, 0))
    y += vh + 30
    d.rectangle([W / 2 - 80, y - 14, W / 2 + 80, y - 8], fill=accent)
    for line in llines:
        d.text((W / 2, y + 10), line, font=lf, fill=(240, 240, 240), anchor="mt")
        y += lf.size * 1.2
    if H > W:
        img = _title_band(img, title, accent)
    img.save(out, quality=95)
    return out


# ---------- segments --------------------------------------------------------
def ken_burns(img, frames, W, H, fps, motion, out, strength=0.12):
    n = max(frames - 1, 1)
    k = strength
    z, x, y = {
        "zoom_in":  (f"1+{k}*on/{n}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        "zoom_out": (f"{1 + k}-{k}*on/{n}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        "pan_right": (f"{1 + k}", f"(iw-iw/zoom)*on/{n}", "ih/2-(ih/zoom/2)"),
        "pan_left":  (f"{1 + k}", f"(iw-iw/zoom)*(1-on/{n})", "ih/2-(ih/zoom/2)"),
    }[motion]
    vf = (f"scale={W * 2}:{H * 2}:flags=lanczos,"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={fps},setsar=1,format=yuv420p")
    _run(["ffmpeg", "-y", "-i", img, "-vf", vf, "-frames:v", frames,
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", out])


def title_overlay(W, H, title, accent, out):
    """Transparent PNG: soft top shade + hook title, laid over panning footage on Shorts."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(shade)
    top = int(H * 0.32)
    for y in range(top):
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(170 * (1 - y / top))))
    img = Image.alpha_composite(img, shade)
    img = _title_band(img, title, accent)
    img.save(out)
    return out


def pan_seg(img, frames, W, H, fps, direction, out, overlay=None):
    """Vertical frame sliding across a wide (16:9) image: how the long video's pictures become Shorts."""
    n = max(frames - 1, 1)
    x = f"(iw-{W})*n/{n}" if direction % 2 == 0 else f"(iw-{W})*(1-n/{n})"
    vf = f"scale=-2:{H}:flags=lanczos,crop={W}:{H}:x='{x}':y=0,setsar=1"
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", img]
    if overlay:
        cmd += ["-i", overlay, "-filter_complex", f"[0:v]{vf}[b];[b][1:v]overlay=0:0,format=yuv420p,fps={fps}"]
    else:
        cmd += ["-vf", f"{vf},format=yuv420p,fps={fps}"]
    _run(cmd + ["-frames:v", frames, "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", out])


def stock_seg(clip, frames, W, H, fps, out):
    dur = _duration(clip)
    need = frames / fps
    ss = random.uniform(0, max(0.0, dur - need - 0.5)) if dur > need + 1 else 0
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},"
          f"fps={fps},setsar=1,format=yuv420p")
    _run(["ffmpeg", "-y", "-ss", f"{ss:.2f}", "-stream_loop", "-1", "-i", clip,
          "-frames:v", frames, "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", out])


def _beats(scenes):
    """Flatten to beats. Accepts: a flat beat list (Short), scenes with 'beats' (long), or the old
    {'narration','visual'} scene format."""
    from .script_gen import _norm_beat
    scenes = [(_norm_beat(x) or {}) if isinstance(x, str) else x for x in (scenes or [])]
    if scenes and all(isinstance(x, dict) and "text" in x for x in scenes):
        groups, titles = [scenes], [None]
    else:
        groups, titles = [], []
        for sc in scenes:
            titles.append(sc.get("title"))
            if "beats" in sc:
                groups.append(sc["beats"])
            else:
                v = sc.get("visual", {})
                shot = {"type": "ai", "prompt": (v.get("prompts") or [v.get("query", "")])[0]} \
                    if isinstance(v, dict) else {"type": "stock", "query": v}
                groups.append([{"text": sc.get("narration", ""), "emotion": "neutral", "shot": shot}])
    out = []
    for gi, g in enumerate(groups):
        g = [b for b in g if (b.get("text") or "").strip()]
        for j, b in enumerate(g):
            out.append(dict(b, scene_end=(j == len(g) - 1 and gi < len(groups) - 1), scene=gi,
                            scene_title=titles[gi] if gi < len(titles) else None))
    return out


_STOP = set("a an the of in on at with and or to for from by is are was were his her their its this that "
             "shot medium wide close up close-up photo realistic natural light lighting soft background "
             "documentary camera angle view scene".split())


def _keywords(text, n=4):
    words = [w for w in re.findall(r"[A-Za-z]+", text.lower()) if w not in _STOP and len(w) > 2]
    return " ".join(words[:n]) or "city street"


def _is_wide(path):
    with Image.open(path) as im:
        return im.width > im.height * 1.2


def build_video(scenes, ch, stock, imggen, workdir, vertical, vcfg, out_name, title=None, cast=None, effects=False,
                info=None, image_pool=None, photos=None, photo_pool=None):
    """info (dict, filled in): chapters [(title, start_s)], scene_images {chapter: [paths]}, length.
    image_pool: pictures for {"type": "image"} shots (Shorts cut from the long video)."""
    wd = Path(workdir); wd.mkdir(parents=True, exist_ok=True)
    W, H = (1080, 1920) if vertical else (1920, 1080)
    fps = vcfg["fps"]
    accent = tuple(ch.get("accent", [255, 214, 0]))
    imggen.budget = vcfg["ai_images_short" if vertical else "ai_images_long"]
    imggen.count = imggen.calls = 0
    imggen.klein_used = 0
    sound = SoundDesign()
    cast_txt = {k.lower(): v for k, v in (cast or {}).items()}

    def with_cast(p):  # keep recurring characters looking the same
        for name, look in cast_txt.items():
            if name in p.lower() and look.lower() not in p.lower():
                p = f"{p}, {name} is a {look}"
        return p

    beats = _beats(scenes)
    t, frame_pos, words_all, wavs, segs, events = 0.0, 0, [], [], [], []
    last_img, mi, pi, cur_scene = None, 0, 0, None
    info = info if info is not None else {}
    info.setdefault("chapters", []); info.setdefault("scene_images", {})
    pool = [p for p in (image_pool or []) if Path(p).exists()]
    overlay = title_overlay(W, H, title, accent, wd / "overlay.png") if vertical else None

    def show(img_path, frames, seg, motion, strength, i):
        if str(img_path).endswith(".mp4"):     # reused real video clip
            stock_seg(img_path, frames, W, H, fps, seg)
            return
        if vertical and _is_wide(img_path):
            pan_seg(img_path, frames, W, H, fps, i, seg, overlay)
        else:
            ken_burns(prep_still(img_path, W, H, wd / f"s{i:03}.jpg", vertical, title, accent),
                      frames, W, H, fps, motion, seg, strength)

    for i, b in enumerate(beats):
        if b.get("scene") != cur_scene:
            cur_scene = b.get("scene")
            info["chapters"].append((b.get("scene_title") or f"Part {len(info['chapters']) + 1}", t))
        emo = b.get("emotion", "neutral")
        mp3, wav = wd / f"b{i:03}.mp3", wd / f"b{i:03}.wav"
        words, pause = synth_beat(b["text"], ch["voice"], ch.get("rate", "+0%"), emo, str(mp3))
        dur = _duration(mp3)
        if not words:
            words = estimate_words(b["text"], dur)
        pause += SCENE_GAP if b.get("scene_end") else 0
        _run(["ffmpeg", "-y", "-i", mp3, "-af", f"apad=pad_dur={pause:.2f}", "-ar", "48000", "-ac", "1", wav])
        seg_len = _duration(wav)
        words_all += [(s + t, e + t, w) for s, e, w in words]
        wavs.append(wav)

        shot = b.get("shot") or {"type": "hold"}
        kind = shot.get("type", "hold")
        sfx = (b.get("sfx") or "none").lower()
        if effects and sfx not in ("none", ""):   # off by default; real recordings in assets/sfx work best
            events.append((t + 0.1, sfx))

        # visual for this beat (exact frame count keeps picture and voice in sync)
        frame_end = round((t + seg_len) * fps)
        frames = max(frame_end - frame_pos, 1)
        seg = wd / f"v{i:03}.mp4"
        motion = MOTIONS[mi % 4] if not vertical else ("zoom_in", "zoom_out")[mi % 2]
        strength = 0.08 if not vertical else 0.06  # slow, documentary-style camera
        mi += 1
        try:
            if kind == "ai":
                try:
                    if imggen.dead >= {"klein", "schnell"}:
                        raise RuntimeError("AI quota used up today")
                    src = imggen.generate(with_cast(shot.get("prompt", b["text"])), vertical)
                except Exception:  # noqa: BLE001  -> real photo or clip of the same idea
                    q = _keywords(shot.get("prompt") or b["text"])
                    src = None
                    if photos is not None:
                        try:
                            src = photos.find(q, vertical)
                        except Exception:  # noqa: BLE001
                            src = None
                    if src is None:
                        src = stock.clip(q, vertical)   # raises -> hold below
                    print(f"[video] AI unavailable -> real {'clip' if str(src).endswith('.mp4') else 'photo'} for '{q}'")
                last_img = src
                info["scene_images"].setdefault(b.get("scene", 0), []).append(str(src))
                show(src, frames, seg, motion, strength, i)
            elif kind == "photo" and photos is not None:
                ref, item = str(shot.get("ref") or ""), None
                if ref[1:].isdigit() and 0 < int(ref[1:]) <= len(photo_pool or []):
                    item = photo_pool[int(ref[1:]) - 1]
                try:
                    src = photos.fetch(item) if item else photos.find(shot.get("query") or b["text"][:60], vertical)
                except Exception:  # noqa: BLE001  no real photo -> AI picture of the same thing
                    src = imggen.generate(with_cast(f"{shot.get('query') or b['text']}, documentary photo"), vertical)
                last_img = src
                info["scene_images"].setdefault(b.get("scene", 0), []).append(str(src))
                show(src, frames, seg, motion, strength, i)
            elif kind == "image" and pool:
                last_img = pool[pi % len(pool)]; pi += 1
                show(last_img, frames, seg, motion, strength, i)
            elif kind == "stat":
                card = stat_card(str(shot.get("value", "")), str(shot.get("label", "")), W, H, accent,
                                 wd / f"c{i:03}.jpg", bg=last_img if last_img and not str(last_img).endswith(".mp4")
                                 else None, title=title)
                ken_burns(card, frames, W, H, fps, "zoom_in", seg, 0.06)
            elif kind == "stock":
                try:
                    clip = stock.clip(shot.get("query", "city night"), vertical)
                    stock_seg(clip, frames, W, H, fps, seg)
                    info["scene_images"].setdefault(b.get("scene", 0), []).append(str(clip))
                except Exception:  # noqa: BLE001  no clip -> real photo -> AI
                    try:
                        src = photos.find(shot.get("query") or b["text"][:60], vertical) if photos else None
                    except Exception:  # noqa: BLE001
                        src = None
                    src = src or imggen.generate(with_cast(f"{shot.get('query')}, documentary photo"), vertical)
                    last_img = src
                    info["scene_images"].setdefault(b.get("scene", 0), []).append(str(src))
                    show(src, frames, seg, motion, strength, i)
            else:
                raise LookupError("hold")
        except Exception as e:  # noqa: BLE001  hold / fallback: keep the story's last image moving
            if not isinstance(e, LookupError):
                print(f"[video] {kind} failed ({str(e)[:100]}), holding previous image")
            if last_img is None:  # nothing yet: try one AI image of this beat, else a title card
                try:
                    last_img = imggen.generate(with_cast(shot.get("prompt") or b["text"]), vertical)
                except Exception:  # noqa: BLE001
                    pass
            if last_img is None and pool:
                last_img = pool[pi % len(pool)]; pi += 1
            if last_img:
                show(last_img, frames, seg, motion, strength, i)
            else:
                ken_burns(stat_card(ch.get("name", "").upper(), b["text"][:40], W, H, accent,
                                    wd / f"c{i:03}.jpg", title=title), frames, W, H, fps, "zoom_in", seg, 0.05)
        segs.append(seg)
        frame_pos += frames
        t += seg_len
    info["length"] = t
    print(f"[video] beats: {len(beats)} | AI images: {imggen.count} (generations incl. QC re-rolls: {imggen.calls}, premium: {imggen.klein_used}, ~{imggen.neurons} of 10,000 free units) | length {t:.1f}s")

    (wd / "vlist.txt").write_text("".join(f"file '{s.name}'\n" for s in segs))
    (wd / "alist.txt").write_text("".join(f"file '{a.name}'\n" for a in wavs))
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "vlist.txt", "-c", "copy", "video.mp4"], cwd=wd)
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "alist.txt", "-c:a", "pcm_s16le", "voice.wav"], cwd=wd)
    music = sorted(Path("assets/music").glob("*.mp3"))
    sound.mix(wd / "voice.wav", events, ch.get("mood", "dark"), music, wd, wd / "mix.wav",
              bed_level=vcfg.get("bed_level", 0.06))
    a = accent
    write_ass(words_all, wd / "subs.ass", W, H, vertical, accent_bgr=f"{a[2]:02X}{a[1]:02X}{a[0]:02X}")

    grade = "eq=contrast=1.03:saturation=1.02,vignette=PI/7,noise=alls=3:allf=t"  # subtle, natural
    if has_ass():
        fc = f"[0:v]{grade},ass=subs.ass[v]"
    else:
        print("[video] WARNING: this ffmpeg has no libass -> rendering WITHOUT captions")
        fc = f"[0:v]{grade}[v]"
    fc += ";[1:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    _run(["ffmpeg", "-y", "-i", "video.mp4", "-i", "mix.wav", "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
          "-c:v", "libx264", "-preset", vcfg.get("final_preset", "fast"), "-crf", "19",
          "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", fps,
          "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", out_name], cwd=wd)
    return wd / out_name


def make_thumbnail(photo, text, out, accent=(255, 214, 0)):
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), (15, 15, 15))
    if photo:
        img = ImageEnhance.Brightness(_cover(Image.open(photo), W, H)).enhance(0.85)
        grad = Image.linear_gradient("L").rotate(-90).resize((W, H))  # dark left (text), clear right (subject)
        img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, grad.point(lambda p: int(p * 0.75)))
    d = ImageDraw.Draw(img)
    text = text.upper()
    for size in range(150, 50, -10):
        font = _font(size)
        lines = textwrap.wrap(text, width=max(6, int(760 / (size * 0.62))))
        if len(lines) <= 3 and all(d.textlength(l, font=font) <= 780 for l in lines):
            break
    y = (H - len(lines) * size * 1.1) / 2
    for i, line in enumerate(lines):
        d.text((55, y + i * size * 1.1), line, font=font, fill=accent if i == 0 else (255, 255, 255),
               stroke_width=8, stroke_fill=(0, 0, 0))
    img.save(out, quality=92)
    return out
