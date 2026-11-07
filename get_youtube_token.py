"""Run locally ONCE PER CHANNEL: python get_youtube_token.py
When Google asks, pick the Brand Account channel (Cash & Court / The Rich Loophole).
Copy the printed refresh token into the matching GitHub secret."""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]
flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
print("\nREFRESH TOKEN:\n", creds.refresh_token)
