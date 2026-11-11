"""Posts a Reel via the Instagram Graph API (resumable local upload, no public URL needed).
Instagram's upload server rejects uploads now and then (400): each failure gets a fresh container and a retry."""
import os, time
import requests


def _attempt(g, ig_user, token, path, caption):
    r = requests.post(f"{g}/{ig_user}/media", timeout=60, data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption[:2200],
        "share_to_feed": "true", "access_token": token}).json()
    if "id" not in r:
        raise RuntimeError(f"IG container failed: {r}")
    cid, uri = r["id"], r["uri"]
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        up = requests.post(uri, data=f, timeout=600, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)})
    if not up.ok:
        raise RuntimeError(f"IG upload {up.status_code} ({size // 1024} KB): {up.text[:300]}")

    for _ in range(60):
        s = requests.get(f"{g}/{cid}", params={"fields": "status_code,status", "access_token": token}, timeout=30).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"IG processing error: {s}")
        time.sleep(10)
    else:
        raise RuntimeError("IG processing timed out")

    pub = requests.post(f"{g}/{ig_user}/media_publish", timeout=60,
                        data={"creation_id": cid, "access_token": token}).json()
    if "id" not in pub:
        raise RuntimeError(f"IG publish failed: {pub}")
    return pub["id"]


def upload_reel(ig_user, token, path, caption, version="v21.0", tries=3):
    g = f"https://graph.facebook.com/{version}"
    if not os.path.exists(path) or os.path.getsize(path) < 10_000:
        raise RuntimeError(f"video file missing or empty: {path}")
    last = None
    for k in range(tries):
        try:
            pid = _attempt(g, ig_user, token, path, caption)
            print(f"[ig] published reel {pid}" + (f" (attempt {k + 1})" if k else ""))
            return pid
        except Exception as e:  # noqa: BLE001
            last = e
            if "OAuthException" in str(e) or "access token" in str(e).lower():
                break                       # token problem: retrying won't help
            print(f"[ig] attempt {k + 1} failed: {str(e)[:200]}")
            time.sleep(20 * (k + 1))
    raise RuntimeError(str(last))
