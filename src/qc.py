"""Automatic image quality check with a free vision model (Gemini, Groq backup).
Scores how real the image looks and whether it shows what the sentence says. Never blocks a run."""
import base64, json, os, re
import requests

ASK = """You are a strict photo editor for a documentary channel. The image should show: "{desc}".
Score 1-10 and list concrete problems. Deduct heavily for: garbled or fake-looking text/writing anywhere,
wrong number of fingers or warped hands/faces, melted or nonsensical objects, plastic/CGI "AI look",
a collage / split image / duplicated or repeated halves (score max 3), or not matching the
description. Judge the main subject and action; small background details may differ. 9-10 = could pass as a real news photo and matches; 7 = minor flaws.
Return ONLY JSON: {{"score": <int>, "issues": ["short issue", ...]}}"""


def _parse(t):
    t = re.sub(r"^```(json)?|```$", "", t.strip(), flags=re.M).strip()
    d = json.loads(t[t.find("{"):t.rfind("}") + 1])
    return int(d.get("score", 0)), [str(x) for x in d.get("issues", [])][:4]


def _gemini(img_b64, desc):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("no gemini key")
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
                                    {"text": ASK.format(desc=desc[:400])}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    for m in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite"):
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                          headers={"x-goog-api-key": key}, json=body, timeout=90)
        if r.status_code in (404, 429, 500, 503):
            continue
        r.raise_for_status()
        return _parse(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    raise RuntimeError("gemini vision unavailable")


def _groq(img_b64, desc):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("no groq key")
    r = requests.post("https://api.groq.com/openai/v1/chat/completions", timeout=90,
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": os.environ.get("GROQ_VISION_MODEL", "qwen/qwen3.8-27b"), "temperature": 0,
                            "messages": [{"role": "user", "content": [
                                {"type": "text", "text": ASK.format(desc=desc[:400])},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]}]})
    r.raise_for_status()
    return _parse(r.json()["choices"][0]["message"]["content"])


COLLAGE_WORDS = re.compile(r"(collage|split|grid|panel|duplicat|repeated|separate (shots|photos|frames))", re.I)


def has_seam(data):
    """Pixel test for collages: a hard straight line across (almost) the whole image where two pictures meet."""
    import io
    import numpy as np
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("L")
    im.thumbnail((320, 320))
    a = np.asarray(im, dtype=np.float32)
    for arr in (a, a.T):                              # horizontal seams, then vertical seams
        d = np.abs(np.diff(arr, axis=0))              # change between neighbouring rows
        n = d.shape[0]
        if n < 20:
            continue
        frac = (d > 25).mean(axis=1)                  # share of the row that jumps sharply
        prof = d.mean(axis=1)
        med = float(np.median(prof)) + 1.0
        lo, hi = int(n * 0.15), int(n * 0.85)
        for i in range(lo, hi):
            if frac[i] > 0.6 and prof[i] > 5 * med:
                return True
    return False


def score_image(data, desc):
    """Returns (score 1-10, issues). If no checker is reachable, returns (10, []) so the run continues.
    A 'collage' verdict is only trusted when the pixels actually show a seam (vision models over-report it)."""
    b64 = base64.b64encode(data).decode()
    for fn in (_gemini, _groq):
        try:
            score, issues = fn(b64, desc)
        except Exception:  # noqa: BLE001
            continue
        if any(COLLAGE_WORDS.search(i) for i in issues):
            try:
                seam = has_seam(data)
            except Exception:  # noqa: BLE001
                seam = True
            if not seam:
                rest = [i for i in issues if not COLLAGE_WORDS.search(i)]
                score = max(score, 6 if rest else 8)
                issues = rest + ["(collage claim ignored: no seam in pixels)"]
        return score, issues
    return 10, []
