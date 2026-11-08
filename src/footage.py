"""Free real stock video: Pixabay and/or Pexels (whichever keys exist)."""
import hashlib, os, random
from pathlib import Path
import requests


class Stock:
    def __init__(self, cache_dir, fallbacks):
        key = os.environ.get("PEXELS_API_KEY")
        self.pexels = {"Authorization": key} if key else None
        self.pixabay = os.environ.get("PIXABAY_API_KEY")
        self.cache = Path(cache_dir); self.cache.mkdir(parents=True, exist_ok=True)
        self.fallbacks = fallbacks
        self.used = set()
        self.sources_used = set()

    # ---- search -------------------------------------------------------
    def _pexels_links(self, q, vertical):
        if not self.pexels:
            return []
        r = requests.get("https://api.pexels.com/videos/search", headers=self.pexels, timeout=60,
                         params={"query": q, "orientation": "portrait" if vertical else "landscape",
                                 "per_page": 30, "size": "medium"})
        out = []
        for v in (r.json().get("videos", []) if r.ok else []):
            files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("width")]
            hd = [f for f in files if min(f["width"], f["height"]) >= 1080]
            if hd and v.get("duration", 0) >= 4:
                out.append((f"px{v['id']}", min(hd, key=lambda f: f["width"])["link"]))
        return out

    def _pixabay_links(self, q, vertical):
        if not self.pixabay:
            return []
        r = requests.get("https://pixabay.com/api/videos/", timeout=60,
                         params={"key": self.pixabay, "q": q, "per_page": 30, "safesearch": "true"})
        out = []
        hits = r.json().get("hits", []) if r.ok else []
        for h in hits:
            if h.get("duration", 0) < 4:
                continue
            for size in ("large", "medium"):
                f = h.get("videos", {}).get(size) or {}
                if f.get("url") and min(f.get("width", 0), f.get("height", 0)) >= 720:
                    # vertical videos first for Shorts; landscape ones are centre-cropped
                    out.append(((f["height"] > f["width"]) != vertical, f"pb{h['id']}", f["url"])); break
        return [(i, u) for _, i, u in sorted(out, key=lambda x: x[0])]

    def _download(self, url, ext):
        p = self.cache / (hashlib.md5(url.encode()).hexdigest() + ext)
        if not p.exists():
            with requests.get(url, stream=True, timeout=180) as r:
                r.raise_for_status()
                with open(p, "wb") as f:
                    for c in r.iter_content(1 << 20):
                        f.write(c)
        return p

    def clip(self, query, vertical):
        """One unused HD clip for the query (falls back to channel themes)."""
        for q in (query, random.choice(self.fallbacks), random.choice(self.fallbacks)):
            links = self._pexels_links(q, vertical) + self._pixabay_links(q, vertical)
            fresh = [l for l in links if l[0] not in self.used]
            for vid, url in fresh[:6]:
                try:
                    p = self._download(url, ".mp4"); self.used.add(vid)
                    self.sources_used.add("Pixabay" if vid.startswith("pb") else "Pexels")
                    return p
                except Exception:  # noqa: BLE001
                    continue
        raise RuntimeError(f"no stock clip for '{query}'")

    def photo(self, query):
        if not self.pexels:
            return None
        for q in (query, random.choice(self.fallbacks)):
            r = requests.get("https://api.pexels.com/v1/search", headers=self.pexels, timeout=60,
                             params={"query": q, "orientation": "landscape", "per_page": 10})
            photos = r.json().get("photos", []) if r.ok else []
            if photos:
                return self._download(random.choice(photos[:5])["src"]["large2x"], ".jpg")
        return None
