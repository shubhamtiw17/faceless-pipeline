"""Real photos, free:
1. Wikimedia Commons: the photos used in the story's own Wikipedia article + Commons search (no key).
2. Pixabay photos (PIXABAY_API_KEY) and Unsplash (UNSPLASH_ACCESS_KEY), both optional.
Only freely licensed images are used, and every one is credited in the video description."""
import hashlib, os, re
from pathlib import Path
import requests

WIKI = "https://en.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
HDR = {"User-Agent": "faceless-pipeline/1.0 (automated educational video tool)"}
SKIP = re.compile(r"(logo|icon|flag|symbol|seal|map|signature|wikiquote|commons-|edit-|question_book|ambox|"
                  r"padlock|portal|sound|\.svg$|\.gif$|\.tif)", re.I)
NONFREE = re.compile(r"(non-free|fair use|copyrighted|all rights reserved)", re.I)


def _clean(html):
    return re.sub(r"<[^>]+>", "", html or "").strip()


class RealPhotos:
    def __init__(self, cache_dir="cache/photos"):
        self.cache = Path(cache_dir); self.cache.mkdir(parents=True, exist_ok=True)
        self.unsplash = os.environ.get("UNSPLASH_ACCESS_KEY")
        self.pixabay = os.environ.get("PIXABAY_API_KEY")
        self.credits = {}      # local path -> credit line
        self.used = set()

    # ---------- Wikimedia ----------
    def _info(self, titles):
        """imageinfo for File: titles on Commons -> list of dicts (url, w, h, desc, credit)."""
        out = []
        for i in range(0, len(titles), 40):
            r = requests.get(COMMONS, headers=HDR, timeout=30, params={
                "action": "query", "format": "json", "formatversion": 2, "titles": "|".join(titles[i:i + 40]),
                "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 1920})
            for p in r.json().get("query", {}).get("pages", []):
                ii = (p.get("imageinfo") or [{}])[0]
                meta = ii.get("extmetadata") or {}
                lic = _clean(meta.get("LicenseShortName", {}).get("value", ""))
                if not ii.get("thumburl") or not lic or NONFREE.search(lic) or SKIP.search(p["title"]):
                    continue
                if min(ii.get("width", 0), ii.get("height", 0)) < 700:
                    continue
                artist = _clean(meta.get("Artist", {}).get("value", "")) or "Unknown author"
                desc = _clean(meta.get("ImageDescription", {}).get("value", ""))[:160] or p["title"][5:]
                out.append({"url": ii["thumburl"], "w": ii["width"], "h": ii["height"], "desc": desc,
                            "credit": f"{p['title'][5:]} by {artist[:60]}, {lic}, {ii.get('descriptionurl', '')}"})
        return out

    def article_photos(self, article_title, n=20):
        """Freely licensed photos that appear in the Wikipedia article (the real places, objects, events)."""
        try:
            r = requests.get(WIKI, headers=HDR, timeout=30, params={
                "action": "query", "format": "json", "formatversion": 2, "titles": article_title,
                "prop": "images", "imlimit": 50, "redirects": 1})
            pages = r.json().get("query", {}).get("pages", [])
            files = [im["title"] for im in (pages[0].get("images", []) if pages else [])]
            return self._info([f for f in files if not SKIP.search(f)])[:n]
        except Exception as e:  # noqa: BLE001
            print(f"[photo] article photos unavailable: {str(e)[:80]}")
            return []

    def commons_search(self, query, n=8):
        try:
            r = requests.get(COMMONS, headers=HDR, timeout=30, params={
                "action": "query", "format": "json", "formatversion": 2, "list": "search",
                "srsearch": f"{query} filetype:bitmap", "srnamespace": 6, "srlimit": n})
            titles = [x["title"] for x in r.json().get("query", {}).get("search", [])]
            return self._info(titles)
        except Exception:  # noqa: BLE001
            return []

    # ---------- Pixabay photos ----------
    def pixabay_search(self, query, vertical=False, n=10):
        if not self.pixabay:
            return []
        try:
            r = requests.get("https://pixabay.com/api/", timeout=30, params={
                "key": self.pixabay, "q": query[:100], "image_type": "photo", "safesearch": "true",
                "orientation": "vertical" if vertical else "horizontal", "per_page": n, "min_width": 1200})
            return [{"url": h["largeImageURL"], "w": h.get("imageWidth", 0), "h": h.get("imageHeight", 0),
                     "desc": h.get("tags", query), "credit": f"Image by {h.get('user', 'Unknown')} from Pixabay "
                                                            f"{h.get('pageURL', '')}"}
                    for h in r.json().get("hits", [])]
        except Exception:  # noqa: BLE001
            return []

    # ---------- Unsplash ----------
    def unsplash_search(self, query, vertical=False, n=8):
        if not self.unsplash:
            return []
        try:
            r = requests.get("https://api.unsplash.com/search/photos", timeout=30,
                             headers={"Authorization": f"Client-ID {self.unsplash}"},
                             params={"query": query, "per_page": n,
                                     "orientation": "portrait" if vertical else "landscape"})
            out = []
            for p in r.json().get("results", []):
                u = p.get("user", {})
                out.append({"url": p["urls"]["raw"] + "&w=1920&q=85&fm=jpg", "w": p["width"], "h": p["height"],
                            "desc": p.get("alt_description") or query, "dl": p["links"]["download_location"],
                            "credit": f"Photo by {u.get('name', 'Unknown')} on Unsplash "
                                      f"https://unsplash.com/@{u.get('username', '')}"})
            return out
        except Exception:  # noqa: BLE001
            return []

    # ---------- download ----------
    def fetch(self, item):
        p = self.cache / (hashlib.md5(item["url"].encode()).hexdigest() + ".jpg")
        if not p.exists():
            r = requests.get(item["url"], headers=HDR, timeout=60)
            r.raise_for_status()
            p.write_bytes(r.content)
            if item.get("dl"):  # Unsplash API guideline: register the download
                try:
                    requests.get(item["dl"], headers={"Authorization": f"Client-ID {self.unsplash}"}, timeout=15)
                except Exception:  # noqa: BLE001
                    pass
        self.credits[str(p)] = item["credit"]
        self.used.add(item["url"])
        return p

    def find(self, query, vertical=False, prefer=None):
        """Best unused real photo for a query (article pool first, then Commons, then Unsplash)."""
        for pool in (prefer or [], self.commons_search(query), self.pixabay_search(query, vertical),
                     self.unsplash_search(query, vertical)):
            for item in pool:
                if item["url"] not in self.used:
                    try:
                        return self.fetch(item)
                    except Exception:  # noqa: BLE001
                        continue
        raise LookupError(f"no real photo for '{query}'")
