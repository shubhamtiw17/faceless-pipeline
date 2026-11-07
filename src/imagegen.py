"""Free AI image generation, most realistic first.
1. Cloudflare FLUX.2 Klein 4B: photoreal, native 16:9 / 9:16 sizes (~150 neurons/image -> ~60/day free)
2. Cloudflare FLUX.1 schnell: older, more "AI-looking", square (fallback when Klein fails or quota is low)
3. Pollinations (optional token)"""
import base64, hashlib, os, random, time, urllib.parse
from pathlib import Path
import requests

from .qc import score_image

CF = "https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{model}"
REALISM = ("candid documentary photograph, photojournalism, full-frame DSLR, 35mm lens, natural light, "
           "realistic skin texture, true-to-life muted colours, slight film grain, one clear subject, "
           "shallow depth of field, soft out-of-focus background, uncluttered, real location")


def _cf_creds():
    acct, tok = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_API_TOKEN")
    if not (acct and tok):
        raise RuntimeError("no Cloudflare creds")
    return acct, tok


def _cf_image(r):
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.text[:200]}")
    res = r.json().get("result") or {}
    img = res.get("image") if isinstance(res, dict) else None
    if not img:
        raise RuntimeError(f"no image in response: {str(r.json())[:200]}")
    return base64.b64decode(img)


def _klein(prompt, w, h, steps):
    acct, tok = _cf_creds()
    url = CF.format(acct=acct, model="@cf/black-forest-labs/flux-2-klein-4b")
    hdr = {"Authorization": f"Bearer {tok}"}
    fields = {"prompt": (None, prompt), "width": (None, str(w)), "height": (None, str(h))}
    r = requests.post(url, headers=hdr, files=fields, timeout=180)       # multipart (FLUX.2 style)
    if r.status_code == 400:                                             # some versions take JSON
        r = requests.post(url, headers=hdr, json={"prompt": prompt, "width": w, "height": h}, timeout=180)
    return _cf_image(r)


def _schnell(prompt, steps):
    acct, tok = _cf_creds()
    r = requests.post(CF.format(acct=acct, model="@cf/black-forest-labs/flux-1-schnell"),
                      headers={"Authorization": f"Bearer {tok}"},
                      json={"prompt": prompt, "steps": min(int(steps), 8)}, timeout=120)
    return _cf_image(r)


def _pollinations(prompt, w, h):
    q = urllib.parse.quote(prompt[:900])
    params = {"width": w, "height": h, "model": "flux", "nologo": "true", "seed": random.randint(1, 10**6)}
    headers = {}
    if os.environ.get("POLLINATIONS_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['POLLINATIONS_TOKEN']}"
    r = requests.get(f"https://image.pollinations.ai/prompt/{q}", params=params, headers=headers, timeout=180)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image"):
        raise RuntimeError("pollinations returned non-image")
    return r.content


class ImageGen:
    def __init__(self, cache_dir, style, cfg):
        self.cache = Path(cache_dir); self.cache.mkdir(parents=True, exist_ok=True)
        self.style, self.steps = style, cfg.get("flux_steps", 8)
        self.providers = cfg.get("image_providers", ["klein", "schnell"])
        self.size_long = cfg.get("size_long", [1536, 864])
        self.size_short = cfg.get("size_short", [864, 1536])
        self.budget = 0   # max distinct shots per video
        self.count = 0    # distinct shots made
        self.calls = 0    # API generations incl. QC re-rolls
        self.dead = set()  # providers that failed hard this run (quota/auth) are skipped afterwards
        self.qc = cfg.get("image_qc", True)
        self.qc_min = cfg.get("qc_min_score", 7)
        self.qc_retries = cfg.get("qc_retries", 2)
        self.qc_extra = cfg.get("qc_extra_images", 10)  # extra generations allowed per video for re-rolls

    def generate(self, prompt, vertical):
        if self.count >= self.budget:
            raise RuntimeError("AI image budget used up")
        full = f"{prompt}. {self.style}. {REALISM}"
        w, h = self.size_short if vertical else self.size_long
        out = self.cache / (hashlib.md5(f"{full}{vertical}".encode()).hexdigest() + ".jpg")
        if out.exists():
            return out
        best, tries = None, 1 + (self.qc_retries if self.qc else 0)
        for attempt in range(tries):
            if attempt and self.calls - self.count >= self.qc_extra:
                break  # re-roll allowance for this video used up: keep the best so far
            variant = full if attempt == 0 else f"{full}, {random.choice(['wider shot', 'closer shot', 'side angle', 'eye-level shot'])}"
            try:
                data, used = self._raw(variant, w, h)
            except Exception:  # noqa: BLE001
                if best:
                    break
                raise
            if not self.qc:
                best = (10, data, []); break
            score, issues = score_image(data, prompt)
            print(f"[img] {used} try {attempt + 1}: QC {score}/10 {('- ' + '; '.join(issues))[:90] if issues else ''}")
            if best is None or score > best[0]:
                best = (score, data, issues)
            if score >= self.qc_min:
                break
        out.write_bytes(best[1]); self.count += 1
        return out

    def _raw(self, full, w, h):
        errs = []
        for p in self.providers:
            if p in self.dead:
                continue
            for attempt in range(2):
                try:
                    data = (_klein(full, w, h, self.steps) if p == "klein" else
                            _schnell(full, self.steps) if p in ("schnell", "cloudflare") else
                            _pollinations(full, w, h))
                    self.calls += 1
                    return data, p
                except Exception as e:  # noqa: BLE001
                    errs.append(f"{p}: {e}")
                    if any(c in str(e) for c in ("401", "402", "403", "429", "4006", "quota")):
                        if p in ("klein", "schnell") and any(c in str(e) for c in ("429", "4006", "quota")):
                            print("[img] Cloudflare free daily limit reached (resets 00:00 UTC / 05:30 IST)")
                        self.dead.add(p); break
                    time.sleep(3 * (attempt + 1))
        raise RuntimeError("image gen failed: " + " | ".join(errs)[:400])
