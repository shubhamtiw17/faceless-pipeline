"""Writes the script as BEATS: 1-2 sentences each, with its own emotion (voice), shot (visual) and sound effect.
The visual changes exactly when the beat is spoken, so pictures follow the story sentence by sentence."""
from .llm import generate_json

EMOTIONS = "neutral, tense, dramatic, excited, question, somber"
SFX = "none, gavel, cash, typing, crowd, heartbeat, impact, siren"

BEAT_RULES = """BEAT RULES (most important part):
- A beat = 1-2 short sentences (8-25 words) spoken over ONE shot. The shot MUST literally show what that beat says:
  money / amounts / profits -> stacks of cash, bank vault, wire-transfer screen, checks being signed
  verdict / sentence / judge -> judge's bench, gavel strike, courtroom from the gallery
  lawsuit / filing / lawyers -> lawyer at desk with legal documents, court papers being stamped
  arrest / investigation -> FBI agents at an office door, handcuffs, police lights at night
  victims / losses -> worried elderly couple at kitchen table with bills, empty savings statement
  luxury / rich -> penthouse, private jet interior, yacht deck, watch on wrist
  credit cards / points -> metal card on marble, airport lounge, business-class seat
  AI tools -> laptop with glowing interface in a modern apartment, person working at night
- "emotion" (controls the narrator's voice): one of [{emotions}]. Vary it like a real storyteller:
  calm setup -> tense build-up -> dramatic reveal -> question to the viewer. Never 3 identical in a row.
- "sfx": one of [{sfx}]. Usually "none"; only for a real sound in the scene (gavel on a verdict).
- "shot" is ONE of (prefer REAL photos, they look far more credible than AI):
  {{"type":"photo","ref":"P3"}}  a REAL photo from the list of available photos below (use it when it shows
      the place, object, product or event the beat talks about; each one at most twice).
  {{"type":"photo","query":"2-5 word search"}}  a REAL photo found by search: concrete places and things
      ("New York courthouse", "stack of 100 dollar bills", "1980s electronics store", "stock exchange floor").
      Never search for a person's name.
  {{"type":"stock","query":"2-4 word search"}}  a REAL VIDEO clip (moving footage) for general moments:
      "counting cash", "police car lights night", "busy office", "city traffic", "typing keyboard",
      "courtroom", "stock market screen". Use it for about 30% of beats, it makes the video feel alive.
  {{"type":"ai","prompt":"..."}}  new AI image. Prompt = a REAL-LOOKING news / documentary photo, like Reuters or AP:
      ordinary people, real places, everyday objects, natural light. Subject + action + setting + era + camera distance
      (wide / medium / close-up). Avoid fantasy, glowing, epic or "cinematic" words; keep it plain and believable.
      AI images fail on readable text and detailed hands: never make documents, screens, signs or hands the
      close-up subject. Show money as neat cash stacks, a vault or a bank exterior; a verdict as the judge's bench
      or a courthouse exterior; lawsuits as a lawyer seen from a distance with files on the desk.
      Never real names, logos, brands or readable text; describe people by look (use the cast below, word for word).
  {{"type":"stat","value":"$65 BILLION","label":"max 5 words"}}  big animated number card, for striking figures.
  {{"type":"hold"}}  keep the previous image (camera keeps moving) when the beat continues the same moment.
- Write for a human narrator: contractions, short punchy sentences, rhetorical questions, "..." for a dramatic pause.
  Numbers as spoken ("sixty-five billion dollars"). No headings, emojis or stage directions."""

PICK_PROMPT = """You plan stories for the faceless YouTube channel "{name}".
Audience: {audience}
Content pillars (today prefer: {pillar}):
{pillars}
Already published (do NOT repeat): {history}

Suggest 6 different REAL stories or topics that each have their OWN detailed English Wikipedia article
(famous fraud cases, lawsuits, scandals, financial schemes, tax strategies, programs, companies).
Pick ones with a strong hook and a clear beginning, twist and ending.
Return ONLY JSON: {{"candidates": [{{"topic": "short description", "wikipedia_title": "exact article title"}}]}}"""

PROMPT = """You are the head writer and director of the faceless YouTube channel "{name}".
Audience: {audience}
Tone: {tone}
Content pillars (today prefer: {pillar}):
{pillars}

Titles already published (NEVER repeat or closely copy):
{history}

Today's story is "{topic}". Your ONLY source of facts is this article:
<<<SOURCE: {src_title} ({src_url})
{source}
SOURCE>>>
STRICT: every name, date, amount, charge, verdict and method you state MUST appear in the SOURCE above.
If it is not in the SOURCE, do not say it. No outside facts, no guesses, no invented quotes.
Say "alleged" where the SOURCE says nothing was proven. Tell the story; never give personal financial,
legal or medical advice.

{beat_rules}

Available real photos (use with {{"type":"photo","ref":"P#"}}):
{photos}

Return ONLY JSON:
{{
 "pillar": "...",
 "title": "curiosity-gap YouTube title, max 70 chars",
 "description": "2-3 sentence SEO description",
 "tags": ["10-15 tags"],
 "cast": {{"<role of a recurring person in THIS story>": "<age, hair, clothing - a look you invent, no real name>"}},
{long_block} "short": {{
   "title": "max 60 chars, the hook as a question or shocking fact",
   "caption": "Instagram caption, 1-2 lines",
   "hashtags": ["8 hashtags without #"],
   "beats": [{{"text": "...", "emotion": "dramatic", "sfx": "cash", "shot": {{"type": "ai", "prompt": "..."}}}}]
 }}
}}

The SHORT: 9-12 beats, 110-150 words, about 50 seconds. Beat 1 is the hook (most shocking fact, strongest image).
Use at most 8 "ai" shots and 1-2 "stat" shots; "hold" for the rest. Last beat: "Full story on the channel."
{long_rules}"""

LONG_PROMPT = """You are the head writer and director of the faceless YouTube channel "{name}".
Audience: {audience}
Tone: {tone}

Write the LONG documentary video about THIS story (already chosen, stay on it):
Story: {story}
Your ONLY source of facts:
<<<SOURCE: {src_title} ({src_url})
{source}
SOURCE>>>
STRICT: every name, date, amount, charge, verdict and method MUST appear in the SOURCE. Nothing from outside it.
Recurring people (use these looks word for word in prompts): {cast}

{beat_rules}

LENGTH: 1300-1500 words in 14-18 scenes (chapters) of 5-9 beats each. First beat = hook.
Use at most {max_ai} "ai" shots in total and 6-10 "stat" shots; use "hold" for the rest (never more than 3 holds in a row).
End with a question that makes viewers comment.

Return ONLY JSON:
{{
 "title": "curiosity-gap YouTube title, max 70 chars",
 "description": "2-3 sentence SEO description",
 "tags": ["10-15 tags"],
 "thumbnail_text": "max 4 punchy words",
 "thumbnail_prompt": "realistic news-photo style image prompt for the thumbnail background, subject on the right third",
 "scenes": [{{"beats": [{{"text": "...", "emotion": "neutral", "sfx": "none", "shot": {{"type": "ai", "prompt": "..."}}}}]}}]
}}"""

SHOT_TYPES = {"ai", "stat", "hold", "stock", "photo"}


import re
import unicodedata

_SPACES = dict.fromkeys(map(ord, "\u00a0\u202f\u2007\u2009\u200a\u2002\u2003"), " ")
_SPACES.update({ord("\u2011"): "-", ord("\u2010"): "-", ord("\u200b"): None, ord("\u2060"): None})


def clean_text(t):
    """Plain spaces/hyphens only (LLMs insert invisible characters that make TTS read words wrong)."""
    t = re.sub(r"(?<=[A-Za-z])[\u202f\u200b\u2060](?=[a-z])", "", str(t))   # "Pearl\u202fman" -> "Pearlman"
    t = unicodedata.normalize("NFKC", t).translate(_SPACES)
    return re.sub(r"\s{2,}", " ", t).strip()


def _norm_beat(b):
    """Repairs the small format slips LLMs make. Returns a clean beat dict or None."""
    if isinstance(b, str):
        b = {"text": b}
    if not isinstance(b, dict):
        return None
    text = clean_text(b.get("text") or b.get("narration") or "")
    if not text:
        return None
    shot = b.get("shot")
    if isinstance(shot, str):
        shot = {"type": "ai", "prompt": shot} if len(shot.split()) > 2 else {"type": "hold"}
    if not isinstance(shot, dict) or shot.get("type") not in SHOT_TYPES:
        shot = {"type": "hold"}
    if shot["type"] == "ai" and not shot.get("prompt"):
        shot = {"type": "hold"}
    if shot["type"] == "stat" and not shot.get("value"):
        shot = {"type": "hold"}
    if shot["type"] == "photo" and not (shot.get("ref") or shot.get("query")):
        shot = {"type": "hold"}
    return {"text": text, "emotion": str(b.get("emotion") or "neutral").lower(),
            "sfx": str(b.get("sfx") or "none").lower(), "shot": shot}


def _norm_beats(beats):
    out = [x for x in (_norm_beat(b) for b in (beats or [])) if x]
    if out and out[0]["shot"]["type"] == "hold":   # first beat must show something
        out[0]["shot"] = {"type": "ai", "prompt": out[0]["text"]}
    return out


def _norm_scenes(scenes):
    out = []
    for sc in scenes or []:
        beats = sc.get("beats") if isinstance(sc, dict) else sc if isinstance(sc, list) else [sc]
        nb = _norm_beats(beats)
        if nb:
            out.append({"beats": nb})
    if out and out[0]["beats"][0]["shot"]["type"] == "hold":
        out[0]["beats"][0]["shot"] = {"type": "ai", "prompt": out[0]["beats"][0]["text"]}
    return out


def _ask(prompt, llm_cfg, check, what, tries=3):
    """check(data) -> (score, error_or_None). Keeps the best attempt so one weak answer never kills the run."""
    best, last = None, None
    for i in range(tries):
        try:
            data = generate_json(prompt, llm_cfg)
            score, err = check(data)
            if best is None or score > best[0]:
                best = (score, data)
            if not err:
                return data
            last = err
        except Exception as e:  # noqa: BLE001
            last = str(e)[:200]
        print(f"[script] {what} attempt {i + 1} not ideal ({last}){', asking again' if i < tries - 1 else ''}")
    if best and best[0] > 0:
        print(f"[script] using best {what} attempt")
        return best[1]
    raise RuntimeError(f"could not get a usable {what}: {last}")


def _find_short(d):
    """Accepts the shapes models actually return: {"short":{beats}}, {"Short":...}, top-level beats, etc."""
    if not isinstance(d, dict):
        return None
    for k, v in d.items():
        if k.lower() == "short" and isinstance(v, dict):
            return v
        if k.lower() == "short" and isinstance(v, list):
            return {"beats": v}
    if isinstance(d.get("beats"), list):
        return {"beats": d["beats"], "title": d.get("short_title") or d.get("title")}
    return None


def _make_script(ch, history, llm_cfg, long_form=True, max_ai_long=24, avoid=()):
    """Picks a sourced story, writes the standalone Short and (on long days) the documentary + Shorts series."""
    titles = [h["title"] for h in history][-120:] + list(avoid)
    pillar = ch["pillars"][len(history) % len(ch["pillars"])]
    rules = BEAT_RULES.format(emotions=EMOTIONS, sfx=SFX)
    pillars = "\n".join(f"- {p}" for p in ch["pillars"])
    hist = "; ".join(titles) or "none yet"

    # 0) choose a story that has a real source article
    from . import sources
    used = {h.get("source_title") for h in history} | set(avoid)
    cands = generate_json(PICK_PROMPT.format(name=ch["name"], audience=ch["audience"], pillar=pillar,
                                             pillars=pillars, history=hist), llm_cfg).get("candidates", [])
    cands = [c for c in cands if isinstance(c, dict) and c.get("wikipedia_title") not in used]
    art, cand = sources.find(cands)
    if not art:
        raise RuntimeError("no candidate story had a usable Wikipedia article")
    print(f"[source] {art['title']} ({len(art['text'])} chars) {art['url']}")
    from .realphotos import RealPhotos
    pool = RealPhotos().article_photos(art["title"])
    photos_txt = "\n".join(f"P{i + 1}: {p['desc']}" for i, p in enumerate(pool)) or "(none - use photo queries)"
    print(f"[photo] {len(pool)} free photos in the article")
    src = art["text"][:10000]   # ~2.5k tokens: enough facts, stays inside free rate limits

    # 1) story + Short (always)
    prompt = PROMPT.format(
        name=ch["name"], audience=ch["audience"], tone=ch["tone"], pillar=pillar, pillars=pillars,
        history="\n".join(f"- {t}" for t in titles) or "- (none yet)",
        topic=cand.get("topic") or art["title"], src_title=art["title"], src_url=art["url"], source=src,
        beat_rules=rules, long_block="", long_rules="", photos=photos_txt)

    def check_short(d):
        sh = _find_short(d)
        if sh is None:
            return 0, "no short"
        d["short"] = sh
        sh["beats"] = _norm_beats(sh.get("beats"))
        n = len(sh["beats"])
        return (n if n >= 3 else 0), (None if n >= 6 else f"only {n} usable short beats")
    if long_form:   # documentary day: the Shorts series replaces the standalone Short (saves a call)
        data = {"title": cand.get("topic") or art["title"], "description": cand.get("topic") or art["title"],
                "short": {"beats": []}, "cast": {}}
    else:
        data = _ask(prompt, llm_cfg, check_short, "short script")
    data.setdefault("title", data["short"].get("title", "Untitled"))
    data["source_title"], data["source_text"], data["source_url"] = art["title"], src, art["url"]
    data["photo_pool"], data["_photos_txt"] = pool, photos_txt
    data["references"] = sources.references(art["title"])
    data["sources"] = [f"Wikipedia: {art['title']} - {art['url']}"] + data["references"]
    data.setdefault("description", data["short"].get("caption", ""))
    if not isinstance(data.get("cast"), dict):
        data["cast"] = {}

    # 2) long video + Shorts series about the same story
    if long_form:
        _make_long(ch, data, art, src, rules, llm_cfg, max_ai_long)
    return data


OUTLINE_PROMPT = """You are the head writer of the faceless YouTube channel "{name}" (audience: {audience}; tone: {tone}).
Plan a {minutes}-minute documentary about: {story}

Your ONLY source of facts:
<<<SOURCE: {src_title} ({src_url})
{source}
SOURCE>>>
Use only facts from the SOURCE. Order the chapters like a thriller: hook, background, rise, cracks, collapse,
investigation, verdict/aftermath, lesson.

Return ONLY JSON:
{{"title": "curiosity-gap YouTube title, max 70 chars",
 "description": "2-3 sentence SEO description",
 "tags": ["10-15 tags"],
 "thumbnail_text": "max 4 punchy words",
 "thumbnail_prompt": "realistic news-photo style image for the thumbnail background, subject on the right third",
 "cast": {{"<role of a recurring person>": "<invented look: age, hair, clothing>"}},
 "chapters": [{{"title": "chapter title, max 6 words", "summary": "2-3 sentences: what happens, SOURCE facts only"}}]}}
Exactly {n_ch} chapters."""

CHAPTER_PROMPT = """You are the head writer of the faceless YouTube channel "{name}" (audience: {audience}; tone: {tone}).
Documentary: "{title}". Full chapter plan:
{plan}

Your ONLY source of facts:
<<<SOURCE: {src_title}
{source}
SOURCE>>>
STRICT: every name, date, amount, charge, verdict and method MUST appear in the SOURCE. Nothing from outside it.
Recurring people (use these looks word for word in prompts): {cast}

{beat_rules}

Available real photos (use with {{"type":"photo","ref":"P#"}}):
{photos}
Mix: ~35% "photo", ~30% "stock" video, ~15% "ai" (only moments nothing real can show), rest "hold"/"stat".

Now write ONLY chapters {first} to {last} in full. Each chapter MUST have AT LEAST {words} words of narration
(count them; this is a {minutes}-minute documentary, so go deep: context, people, numbers, turning points) in 10-16 beats,
at most {ai_per} "ai" shots per chapter, 0-1 "stat" shot, "hold" for the rest (never more than 3 holds in a row).
Connect to the previous chapter naturally; end each chapter with a small cliffhanger.{ending}
Return ONLY JSON: {{"chapters": [{{"title": "...", "beats": [{{"text": "...", "emotion": "...", "sfx": "none", "shot": {{"type": "ai", "prompt": "..."}}}}]}}]}}"""

PARTS_PROMPT = """You turn a documentary into a {n} -part YouTube Shorts / Instagram Reels series.
Documentary: "{title}"
Chapters (number: title - narration):
{chapters}

Write {n} parts that together retell the WHOLE story in order. Each part: {w_min}-{w_max} words (60-100 seconds),
covers a consecutive group of chapters, and only uses facts from the narration above.
- Beat 1 of each part = a hook that works for someone who never saw the other parts.
- End each part with a cliffhanger and "Part <next> is on the channel." The last part ends with
  "Watch the full documentary on the channel."
- Beats: 1-2 short sentences each. "shot" is {{"type": "image"}} (shows a picture from those chapters) or
  {{"type": "stat", "value": "$65 BILLION", "label": "max 5 words"}} for a striking number (max 1 per part).
- "emotion": one of [{emotions}].
Return ONLY JSON:
{{"parts": [{{"title": "hook title max 55 chars (Part 1/{n})", "caption": "1-2 lines", "hashtags": ["8 without #"],
   "chapters": [1, 2, 3], "beats": [{{"text": "...", "emotion": "dramatic", "shot": {{"type": "image"}}}}]}}]}}"""


def _make_long(ch, data, art, src, rules, llm_cfg, max_ai):
    """15-20 min documentary written in small calls (outline -> chapter batches) + a Shorts series."""
    lcfg = ch.get("long", {})
    minutes = lcfg.get("minutes", "15-20")
    n_ch = int(lcfg.get("chapters", 12))
    words = int(lcfg.get("words", 2600))
    n_parts = int(lcfg.get("short_parts", 5))
    per_ch = max(120, words // n_ch)
    ai_per = max(2, round(max_ai / n_ch))

    def check_outline(d):
        if not isinstance(d, dict) or not isinstance(d.get("chapters"), list):
            return 0, "no chapters"
        d["chapters"] = [c for c in d["chapters"] if isinstance(c, dict) and c.get("title")]
        n = len(d["chapters"])
        return n, (None if n >= max(6, n_ch - 3) else f"only {n} chapters")
    outline = _ask(OUTLINE_PROMPT.format(name=ch["name"], audience=ch["audience"], tone=ch["tone"], minutes=minutes,
                                         story=f"{data.get('title')} - {data.get('description')}",
                                         src_title=art["title"], src_url=art["url"], source=src, n_ch=n_ch),
                   llm_cfg, check_outline, "long outline")
    for k in ("title", "description", "tags", "thumbnail_text", "thumbnail_prompt"):
        if outline.get(k):
            data[k] = outline[k]
    if isinstance(outline.get("cast"), dict) and outline["cast"]:
        data["cast"] = outline["cast"]
    chapters = outline["chapters"]
    plan = "\n".join(f"{i + 1}. {c['title']}: {c.get('summary', '')}" for i, c in enumerate(chapters))

    scenes, batch = [], 3
    for first in range(1, len(chapters) + 1, batch):
        last = min(first + batch - 1, len(chapters))
        ending = " The final chapter ends with a question that makes viewers comment." if last == len(chapters) else ""

        def check_batch(d, want=last - first + 1):
            if not isinstance(d, dict):
                return 0, "not an object"
            got = _norm_scenes(d.get("chapters") or d.get("scenes"))
            d["_scenes"] = got
            nb = sum(len(sc["beats"]) for sc in got)
            nw = sum(len(b["text"].split()) for sc in got for b in sc["beats"])
            if len(got) < want or nb < 5 * want:
                return nb, f"{len(got)} chapters / {nb} beats"
            if nw < 0.8 * per_ch * want:   # LLMs under-write: ask again until the length is right
                return nw, f"too short: {nw} words, need ~{per_ch * want}"
            return nw, None
        res = _ask(CHAPTER_PROMPT.format(name=ch["name"], audience=ch["audience"], tone=ch["tone"],
                                         title=data["title"], plan=plan, src_title=art["title"], source=src,
                                         cast=data.get("cast") or "none", beat_rules=rules, first=first,
                                         last=last, words=per_ch, ai_per=ai_per, ending=ending, minutes=minutes,
                                         photos=data.get("_photos_txt", "(none)")),
                   llm_cfg, check_batch, f"chapters {first}-{last}")
        raw = (res.get("chapters") or res.get("scenes") or [])
        for j, sc in enumerate(res["_scenes"]):
            t = raw[j].get("title") if j < len(raw) and isinstance(raw[j], dict) else None
            sc["title"] = t or chapters[min(first - 1 + j, len(chapters) - 1)]["title"]
        scenes += res["_scenes"]
    data["scenes"] = scenes
    print(f"[script] long: {len(scenes)} chapters, {sum(len(s['beats']) for s in scenes)} beats, "
          f"{sum(len(b['text'].split()) for s in scenes for b in s['beats'])} words")
    data.setdefault("thumbnail_text", data["title"][:30])
    data["parts"] = make_parts(data, llm_cfg, n_parts)


def make_parts(data, llm_cfg, n=5):
    """Shorts series (Part 1..n) retelling the long video; pictures come from the long video's chapters."""
    lcfg_words = (150, 230)
    chap_txt = "\n".join(f"{i + 1}: {sc.get('title', '')} - " + " ".join(b["text"] for b in sc["beats"])
                         for i, sc in enumerate(data["scenes"]))

    def check_parts(d):
        if not isinstance(d, dict) or not isinstance(d.get("parts"), list):
            return 0, "no parts"
        good = []
        for p in d["parts"]:
            if not isinstance(p, dict):
                continue
            beats = []
            for b in p.get("beats") or []:
                nb = _norm_beat(b if not isinstance(b, dict) or b.get("shot", {}).get("type") != "image"
                                else {**b, "shot": {"type": "hold"}})
                if nb:
                    if isinstance(b, dict) and (b.get("shot") or {}).get("type") == "image":
                        nb["shot"] = {"type": "image"}
                    elif nb["shot"]["type"] != "stat":
                        nb["shot"] = {"type": "image"}
                    beats.append(nb)
            if len(beats) >= 4:
                ch_ids = [int(x) for x in p.get("chapters") or [] if str(x).isdigit()]
                good.append({"title": str(p.get("title") or data["title"])[:90], "caption": p.get("caption", ""),
                             "hashtags": p.get("hashtags") or [], "chapters": ch_ids, "beats": beats})
        d["parts"] = good
        return len(good), (None if len(good) >= max(3, n - 1) else f"only {len(good)} parts")
    res = _ask(PARTS_PROMPT.format(n=n, title=data["title"], chapters=chap_txt, w_min=lcfg_words[0],
                                   w_max=lcfg_words[1], emotions=EMOTIONS), llm_cfg, check_parts, "shorts series")
    parts = res["parts"]
    total = len(data["scenes"])
    for k, p in enumerate(parts):  # fill missing chapter ranges evenly
        if not p["chapters"]:
            a, b = k * total // len(parts), (k + 1) * total // len(parts)
            p["chapters"] = list(range(a + 1, max(a + 1, b) + 1))
    print(f"[script] shorts series: {len(parts)} parts, " +
          ", ".join(str(sum(len(b['text'].split()) for b in p['beats'])) + "w" for p in parts))
    return parts


def make_script(ch, history, llm_cfg, long_form=True, max_ai_long=24):
    """Writes the script, then fact-checks it. A story the checker rejects is replaced (max 3 stories)."""
    from .factcheck import check_script
    avoid = []
    for attempt in range(3):
        data = _make_script(ch, history, llm_cfg, long_form, max_ai_long, avoid)
        try:
            if check_script(data, llm_cfg):
                return data
        except Exception as e:  # noqa: BLE001 - checker down: keep script, flag it
            print(f"[fact] check unavailable ({str(e)[:100]}) - review this script manually")
            data["factcheck"] = {"error": str(e)[:200]}
            return data
        print(f"[fact] story rejected: {data.get('title')!r} - writing a different one")
        avoid.append(str(data.get("source_title")))
    raise RuntimeError("3 stories failed fact-check")
