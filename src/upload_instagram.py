"""Posts a Reel via the Instagram Graph API (resumable local upload, no public URL needed)."""
import os, time
import requests


def upload_reel(ig_user, token, path, caption, version="v21.0"):
    g = f"https://graph.facebook.com/{version}"
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
    up.raise_for_status()

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
    print(f"[ig] published reel {pub['id']}")
    return pub["id"]
