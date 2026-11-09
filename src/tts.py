"""Expressive narration with free edge-tts neural voices.
Each beat is spoken with its own speed / pitch / loudness from its emotion, followed by a natural pause,
so the delivery rises and falls like a human storyteller instead of one flat read."""
import asyncio, re
import edge_tts

# emotion -> (rate delta %, pitch Hz, volume %, pause after in seconds)
PROSODY = {
    "neutral":  (0,   0,  0, 0.25),
    "tense":    (-6, -2, -4, 0.40),
    "dramatic": (-12, -4, 0, 0.75),
    "excited":  (8,   4,  4, 0.15),
    "question": (-3,  3,  0, 0.55),
    "somber":   (-10, -5, -8, 0.55),
}


def _pct(v):
    return f"{'+' if v >= 0 else ''}{int(v)}%"


async def _synth(text, voice, rate, pitch, volume, mp3):
    words = []
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume, boundary="WordBoundary")
    with open(mp3, "wb") as f:
        async for c in comm.stream():
            if c["type"] == "audio":
                f.write(c["data"])
            elif c["type"] == "WordBoundary":
                s = c["offset"] / 1e7
                words.append((s, s + c["duration"] / 1e7, c["text"]))
    return words


def estimate_words(text, dur):
    """Fallback word timings (some voices send no word boundaries): spread by word length."""
    toks = text.split()
    if not toks:
        return []
    w = [len(t) + 2 for t in toks]
    scale, t, out = dur * 0.96 / sum(w), 0.02, []
    for tok, wt in zip(toks, w):
        out.append((t, t + wt * scale * 0.9, tok)); t += wt * scale
    return out


BACKUP_VOICES = ["en-US-GuyNeural", "en-US-AriaNeural", "en-US-ChristopherNeural"]


def synth_beat(text, voice, base_rate, emotion, mp3):
    """Writes mp3. Returns (word timings or [], pause_after_seconds).
    Microsoft's free TTS sometimes returns no audio (throttling): wait and retry, then plain prosody,
    then backup voices. Never lets one sentence crash a whole video."""
    import time
    dr, dp, dv, pause = PROSODY.get(emotion, PROSODY["neutral"])
    base = int(re.sub(r"[^-\d]", "", base_rate or "0") or 0)
    if text.rstrip().endswith("?"):
        dp, pause = max(dp, 2), max(pause, 0.45)
    text = re.sub(r"[*_#<>{}\[\]|~^]", " ", text)          # symbols some voices choke on
    if not re.search(r"[A-Za-z0-9]", text):
        text = "..."
    attempts = [(voice, _pct(base + dr), f"{'+' if dp >= 0 else ''}{dp}Hz", _pct(dv))] * 3 + \
               [(voice, "+0%", "+0Hz", "+0%")] + [(v, "+0%", "+0Hz", "+0%") for v in BACKUP_VOICES]
    last = None
    for k, (v, rate, pitch, vol) in enumerate(attempts):
        try:
            words = asyncio.run(_synth(text, v, rate, pitch, vol, mp3))
            if k:
                print(f"[tts] recovered on attempt {k + 1} ({v})")
            return words, pause
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(min(2 * (k + 1), 10))
    raise RuntimeError(f"TTS failed after {len(attempts)} attempts: {last}")
