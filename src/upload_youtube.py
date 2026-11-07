import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]


def service(refresh_token):
    creds = Credentials(None, refresh_token=refresh_token, token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                        scopes=SCOPES)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(svc, path, title, description, tags, privacy, category, thumbnail=None, publish_at=None):
    """publish_at (datetime, UTC): upload now as private, YouTube makes it public at that time."""
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
    if publish_at and privacy == "public":
        status = {"privacyStatus": "private", "publishAt": publish_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "selfDeclaredMadeForKids": False}
    body = {"snippet": {"title": title[:100], "description": description.replace("<", "(").replace(">", ")")[:4900],
                        "tags": tags[:30], "categoryId": category}, "status": status}
    req = svc.videos().insert(part="snippet,status", body=body,
                              media_body=MediaFileUpload(str(path), chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    if thumbnail:
        try:  # needs a phone-verified channel
            svc.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumbnail))).execute()
        except Exception as e:  # noqa: BLE001
            print(f"[yt] thumbnail skipped: {e}")
    print(f"[yt] uploaded https://youtu.be/{vid}" + (f" (goes public {publish_at:%Y-%m-%d %H:%M} UTC)" if publish_at
                                                      and privacy == "public" else f" ({privacy})"))
    return vid
