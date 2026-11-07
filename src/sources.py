"""Real source documents for every story (free, no key): Wikipedia's API.
The script may only use facts that appear in the downloaded text."""
import re
import requests

API = "https://en.wikipedia.org/w/api.php"
HDR = {"User-Agent": "faceless-pipeline/1.0 (automated educational video tool)"}


def _get(params):
    r = requests.get(API, params={**params, "format": "json", "formatversion": 2}, headers=HDR, timeout=30)
    r.raise_for_status()
    return r.json()


def search(query, n=5):
    d = _get({"action": "query", "list": "search", "srsearch": query, "srlimit": n})
    return [x["title"] for x in d.get("query", {}).get("search", [])]


def article(title):
    """Returns {'title','url','text'} or None. Follows redirects; skips disambiguation pages."""
    d = _get({"action": "query", "prop": "extracts|pageprops", "explaintext": 1, "redirects": 1, "titles": title})
    pages = d.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing") or "disambiguation" in (pages[0].get("pageprops") or {}):
        return None
    p = pages[0]
    text = re.sub(r"\n{3,}", "\n\n", p.get("extract", ""))
    # drop reference-ish tail sections
    text = re.split(r"\n== ?(See also|References|Notes|External links|Further reading) ?==", text)[0]
    return {"title": p["title"], "url": "https://en.wikipedia.org/wiki/" + p["title"].replace(" ", "_"),
            "text": text.strip()}


def find(candidates, min_chars=2500):
    """candidates: [{'topic','wikipedia_title'}]. Returns the first usable article (+ its candidate) or None."""
    for c in candidates:
        for t in [c.get("wikipedia_title")] + search(c.get("topic") or c.get("wikipedia_title") or "", 3):
            if not t:
                continue
            try:
                a = article(t)
            except Exception:  # noqa: BLE001
                continue
            if a and len(a["text"]) >= min_chars:
                return a, c
    return None, None


TRUSTED = ["justice.gov", "sec.gov", "fbi.gov", "ftc.gov", "irs.gov", "treasury.gov", "congress.gov", "gao.gov",
           "uscourts.gov", "supremecourt.gov", "courtlistener.com", "law.cornell.edu", ".gov",
           "reuters.com", "apnews.com", "bbc.co.uk", "bbc.com", "nytimes.com", "wsj.com", "washingtonpost.com",
           "bloomberg.com", "ft.com", "theguardian.com", "cnbc.com", "npr.org", "propublica.org", "forbes.com",
           "economist.com", "cnn.com", "nbcnews.com", "cbsnews.com", "abcnews.go.com", "latimes.com",
           "icij.org", "politico.com", "fortune.com", "businessinsider.com", "time.com", "theatlantic.com"]
SKIP = ["wikipedia.org", "wikimedia.org", "wikidata.org", "archive.org", "archive.today", "doi.org", "worldcat.org",
        "google.com", "books.google", "jstor.org", "imdb.com", "twitter.com", "x.com", "facebook.com", "youtube.com"]


def references(title, n=15):
    """The external sources the article cites, most trustworthy first (court, government, major news)."""
    try:
        d = _get({"action": "parse", "page": title, "prop": "externallinks", "redirects": 1})
    except Exception:  # noqa: BLE001
        return []
    links = [u for u in d.get("parse", {}).get("externallinks", []) if u.startswith("http")]
    host_of = lambda u: re.sub(r"^https?://(www\.)?", "", u).split("/")[0].lower()  # noqa: E731
    links = [u for u in dict.fromkeys(links)
             if not any(host_of(u) == s or host_of(u).endswith("." + s) or s in u for s in SKIP if "." in s)]

    def rank(u):
        host = host_of(u)
        for i, t in enumerate(TRUSTED):
            if host.endswith(t) or (t.startswith(".") and host.endswith(t)):
                return i
        return len(TRUSTED)
    links.sort(key=rank)
    return links[:n]
