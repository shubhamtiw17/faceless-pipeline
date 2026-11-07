# Faceless Pipeline — Cash & Court & The Rich Loophole

Daily, on GitHub Actions (free): LLM script → AI voice → Pexels B-roll → captions → upload to YouTube (long + Short) and Instagram (Reel).

| Step | Tool (free) |
|---|---|
| Script | Gemini 2.5 Flash (main), Groq Llama 3.3 (backup) |
| Voice + captions | edge-tts |
| Visuals | Cloudflare FLUX AI images (Ken Burns motion) + HD Pexels/Pixabay clips + animated stat cards |
| Captions | Word-by-word highlighted (ASS) |
| Editing | ffmpeg |
| Upload | YouTube Data API, Instagram Graph API |

## Schedule
- Runs 17:00 UTC (12:00 ET) daily, both channels.
- Short + Reel every day; long-form on `long_days` in `config.yaml`.
- Uploads go out as **private** until you set `youtube.privacy: public`.

## Quick commands
| Command | Does |
|---|---|
| `python check_setup.py` | Tests every key/token, prints PASS/FAIL/SKIP |
| `python -m src.main --channel cash_and_court --short-only --dry-run` | Fast test: one Short, no upload (~3 min) |
| `python -m src.main --channel cash_and_court --force-long --dry-run` | Full test: long + Short, no upload |

Full step-by-step setup is in the Setup Guide doc. Copy `.env.example` to `.env` for local runs.

## One-time setup (~1 hour)

### 1. Free API keys
| Secret | Where |
|---|---|
| `GEMINI_API_KEY` | aistudio.google.com → Get API key |
| `GROQ_API_KEY` | console.groq.com → API Keys |
| `PEXELS_API_KEY` | pexels.com/api |

### 2. YouTube
1. console.cloud.google.com → new project → enable **YouTube Data API v3**.
2. OAuth consent screen → External → add yourself as test user → **Publish app** (otherwise tokens expire every 7 days).
3. Credentials → OAuth client ID → **Desktop app** → download as `client_secret.json`.
4. Locally: `pip install google-auth-oauthlib && python get_youtube_token.py` — run **twice**, choosing a different channel each time.
5. Secrets: `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_TOKEN_CASH_AND_COURT`, `YT_TOKEN_RICH_LOOPHOLE`.
6. Verify each channel by phone (youtube.com/verify) so custom thumbnails work.
7. **Apply for the API audit** (YouTube API Services compliance form). Until it's approved, API uploads are locked to private.

### 3. Instagram (per account)
1. Instagram account set to **Business**, linked to its Facebook Page.
2. developers.facebook.com → create app (Business) → add **Instagram Graph API**.
3. Graph API Explorer → permissions `instagram_basic, instagram_content_publish, pages_show_list, pages_read_engagement` → generate token → exchange for a long-lived token → get the **Page access token** (doesn't expire).
4. `GET /me/accounts?fields=instagram_business_account` → that id is the IG user id.
5. Secrets: `IG_USER_CASH_AND_COURT`, `IG_TOKEN_CASH_AND_COURT`, `IG_USER_RICH_LOOPHOLE`, `IG_TOKEN_RICH_LOOPHOLE`.

### 4. Repo
Push this folder to a **private** GitHub repo → Settings → Secrets and variables → Actions → add all secrets above.

## Test
Actions → Faceless Pipeline → Run workflow → `dry_run: true`, `force_long: true`. Download the videos from the run's artifacts and review.

## Optional
Drop royalty-free `.mp3` tracks (YouTube Audio Library) into `assets/music/` for background music.

## Limits to know
| Limit | Value |
|---|---|
| YouTube API quota | 10,000 units/day ≈ 6 uploads/day (we use ≤ 4) |
| Gemini free tier | enough for ~2 scripts/day |
| Actions minutes | unlimited on public repos; 2,000/month on private (≈ 15–25 min/run) |
