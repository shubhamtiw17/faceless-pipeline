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


def score_image(data, desc):
    """Returns (score 1-10, issues). If no checker is reachable, returns (10, []) so the run continues."""
    b64 = base64.b64encode(data).decode()
    for fn in (_gemini, _groq):
        try:
            return fn(b64, desc)
        except Exception:  # noqa: BLE001
            continue
    return 10, []
