"""LLM calls: Gemini (main) -> Groq (backup). Always returns parsed JSON.
Also search_json(): Gemini with live Google Search, used for fact-checking."""
import json, os, re, time
import requests

GEMINI_FALLBACKS = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
_gemini_down_until = 0.0   # when every Gemini model is busy, skip Gemini for a few minutes


def _gemini_call(body, model):
    global _gemini_down_until
    if time.time() < _gemini_down_until:
        raise RuntimeError("gemini skipped (busy a moment ago)")
    key = os.environ["GEMINI_API_KEY"]
    last = None
    for m in [model] + [x for x in GEMINI_FALLBACKS if x != model]:
        r = requests.post(GEMINI_URL.format(m=m), headers={"x-goog-api-key": key}, json=body, timeout=300)
        if r.status_code in (404, 429, 500, 503):  # not offered / rate-limited / overloaded -> next model
            last = f"{m}: {r.status_code}"; continue
        if not r.ok:
            raise RuntimeError(f"{m}: {r.status_code} {r.text[:300]}")
        parts = r.json()["candidates"][0]["content"].get("parts", [])
        return "".join(p.get("text", "") for p in parts)
    _gemini_down_until = time.time() + 300
    raise RuntimeError(f"all Gemini models busy/unavailable ({last})")


def _gemini(prompt, model):
    return _gemini_call({"contents": [{"parts": [{"text": prompt}]}],
                         "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9}}, model)


GROQ_FALLBACKS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]


def _groq(prompt, model):
    """On a rate limit (429) the next free Groq model is tried, so one model's quota never stops a run."""
    hdr = {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"}
    last = None
    for m in [model] + [x for x in GROQ_FALLBACKS if x != model]:
        body = {"model": m, "temperature": 0.8, "max_completion_tokens": 12000,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}]}
        if "gpt-oss" in m:
            body["reasoning_effort"] = "low"   # leave the output budget for the script, not for thinking
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=hdr, json=body, timeout=300)
        if r.status_code == 400 and "reasoning" in r.text:
            body.pop("reasoning_effort", None)
            r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=hdr, json=body, timeout=300)
        if r.status_code == 429:   # per-minute limit: a short wait usually clears it
            wait = float(r.headers.get("retry-after", 0) or 0)
            if 0 < wait <= 30:
                time.sleep(wait + 1)
                r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=hdr, json=body,
                                  timeout=300)
        if r.status_code in (404, 413, 429, 503):   # unavailable / too big / rate-limited -> next model
            last = f"{m}: {r.status_code}"
            continue
        if not r.ok:
            raise RuntimeError(f"groq {r.status_code}: {r.text[:300]}")
        if m != model:
            print(f"[llm] groq fell back to {m}")
        return r.json()["choices"][0]["message"]["content"]
    raise RuntimeError(f"groq: all models rate-limited ({last}) - free daily limit, resets in a few hours")


def _parse(text):
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(text[text.find("{"):text.rfind("}") + 1])


def generate_json(prompt, cfg):
    errors = []
    for name, fn, model in (("gemini", _gemini, cfg["gemini_model"]),
                            ("groq", _groq, cfg["groq_model"])):
        if not os.environ.get(f"{name.upper()}_API_KEY"):
            continue
        for attempt in range(3):
            try:
                out = _parse(fn(prompt, model))
                print(f"[llm] {name} ok")
                return out
            except Exception as e:  # noqa: BLE001
                errors.append(f"{name}#{attempt}: {str(e)[:150]}")
                if "busy" in str(e) or "skipped" in str(e):
                    break                      # don't hammer a busy Gemini, go to Groq
                time.sleep(4 * (attempt + 1))
    raise RuntimeError("All LLMs failed: " + " | ".join(errors))


def search_json(prompt, cfg):
    """Gemini + live Google Search grounding. Returns parsed JSON or None if unavailable."""
    if not os.environ.get("GEMINI_API_KEY"):
        return None
    body = {"contents": [{"parts": [{"text": prompt + "\nReply with ONLY the JSON object, no other text."}]}],
            "tools": [{"google_search": {}}], "generationConfig": {"temperature": 0}}
    for attempt in range(2):
        try:
            out = _parse(_gemini_call(body, cfg["gemini_model"]))
            print("[llm] gemini + google search ok")
            return out
        except Exception as e:  # noqa: BLE001
            if "busy" in str(e) or "skipped" in str(e):
                return None
            time.sleep(5)
    return None
