"""Checks every credential one by one and prints PASS / FAIL / SKIP.
Usage:  python check_setup.py            (all checks)
        python check_setup.py cloudflare youtube   (only some)
Reads keys from environment variables (or a local .env file)."""
import base64, os, shutil, sys
from pathlib import Path
import requests

if Path(".env").exists():  # simple KEY=VALUE loader
    for line in Path(".env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"'))

E = os.environ.get
results = []


def check(name, needs):
    def deco(fn):
        def run():
            missing = [n for n in needs if not E(n)]
            if missing:
                results.append((name, "SKIP", "missing " + ", ".join(missing))); return
            try:
                results.append((name, "PASS", fn()))
            except Exception as e:  # noqa: BLE001
                results.append((name, "FAIL", str(e)[:200]))
        run.key = name
        return run
    return deco


@check("tools", [])
def tools():
    for t in ("ffmpeg", "ffprobe"):
        if not shutil.which(t):
            raise RuntimeError(f"{t} not installed")
    from src.video import FONT, has_ass
    if not has_ass():
        raise RuntimeError("ffmpeg lacks libass (no captions). Mac fix: brew uninstall ffmpeg && "
                           "brew tap homebrew-ffmpeg/ffmpeg && brew install homebrew-ffmpeg/ffmpeg/ffmpeg")
    if not Path(FONT).exists():
        raise RuntimeError(f"font not found at {FONT} (see guide step 6.2)")
    return "ffmpeg + libass + font ok"


@check("gemini", ["GEMINI_API_KEY"])
def gemini():
    from src.llm import _gemini
    import yaml
    model = yaml.safe_load(open("config.yaml"))["llm"]["gemini_model"]
    _gemini('Return the JSON {"ok": true}', model)
    return "model replied"


@check("groq", ["GROQ_API_KEY"])
def groq():
    r = requests.get("https://api.groq.com/openai/v1/models", timeout=30,
                     headers={"Authorization": f"Bearer {E('GROQ_API_KEY')}"})
    r.raise_for_status(); return f"{len(r.json()['data'])} models available"


@check("pexels", ["PEXELS_API_KEY"])
def pexels():
    r = requests.get("https://api.pexels.com/videos/search", params={"query": "money", "per_page": 1},
                     headers={"Authorization": E("PEXELS_API_KEY")}, timeout=30)
    r.raise_for_status(); return f"{r.json().get('total_results')} results for 'money'"


@check("pixabay", ["PIXABAY_API_KEY"])
def pixabay():
    r = requests.get("https://pixabay.com/api/videos/", params={"key": E("PIXABAY_API_KEY"), "q": "money"}, timeout=30)
    r.raise_for_status(); return f"{r.json().get('total')} results"


@check("cloudflare", ["CF_ACCOUNT_ID", "CF_API_TOKEN"])
def cloudflare():
    from src.imagegen import _klein, _schnell
    p = "an accountant at a cluttered desk reviewing bank statements, documentary photo, natural light"
    try:
        Path("check_image.jpg").write_bytes(_klein(p, 864, 1536, 8)); used = "FLUX.2 Klein (realistic)"
    except Exception as e:  # noqa: BLE001
        Path("check_image.jpg").write_bytes(_schnell(p, 4)); used = f"FLUX.1 schnell only (Klein failed: {str(e)[:80]})"
    return f"{used} -> check_image.jpg, open it"


def _yt(token_var):
    @check(f"youtube:{token_var}", ["YT_CLIENT_ID", "YT_CLIENT_SECRET", token_var])
    def f():
        r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
            "client_id": E("YT_CLIENT_ID"), "client_secret": E("YT_CLIENT_SECRET"),
            "refresh_token": E(token_var), "grant_type": "refresh_token"})
        if not r.ok:
            raise RuntimeError(r.text)
        at = r.json()["access_token"]
        c = requests.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet", "mine": "true"},
                         headers={"Authorization": f"Bearer {at}"}, timeout=30).json()
        return "channel = " + c["items"][0]["snippet"]["title"] + "  (must match the token name!)"
    return f


def _ig(user_var, token_var):
    @check(f"instagram:{user_var}", [user_var, token_var])
    def f():
        r = requests.get(f"https://graph.facebook.com/v21.0/{E(user_var)}", timeout=30,
                         params={"fields": "username", "access_token": E(token_var)})
        if not r.ok:
            raise RuntimeError(r.text)
        return "account = @" + r.json()["username"]
    return f


CHECKS = [tools, gemini, groq, pexels, pixabay, cloudflare,
          _yt("YT_TOKEN_CASH_AND_COURT"), _yt("YT_TOKEN_RICH_LOOPHOLE"),
          _ig("IG_USER_CASH_AND_COURT", "IG_TOKEN_CASH_AND_COURT"),
          _ig("IG_USER_RICH_LOOPHOLE", "IG_TOKEN_RICH_LOOPHOLE")]

if __name__ == "__main__":
    want = sys.argv[1:]
    for c in CHECKS:
        if not want or any(w in c.key for w in want):
            c()
    for name, status, msg in results:
        print(f"{status:5} {name:36} {msg}")
    sys.exit(1 if any(s == "FAIL" for _, s, _ in results) else 0)
