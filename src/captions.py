"""Word-by-word highlighted captions (ASS), the style used by top Shorts/Reels."""


def _ts(t):
    t = max(0.0, t)
    h, rem = divmod(t, 3600); m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02}:{s:05.2f}"


def _clean(w):
    return w.replace("{", "(").replace("}", ")").replace("\\", "")


def write_ass(words, path, W, H, vertical, accent_bgr="00D7FF"):
    size, per, align, margin = (76, 3, 2, 250) if vertical else (60, 6, 2, 70)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{6 if vertical else 4},{2 if vertical else 1},{align},80,80,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    groups = [words[i:i + per] for i in range(0, len(words), per)]
    for gi, g in enumerate(groups):
        nxt = groups[gi + 1][0][0] if gi + 1 < len(groups) else g[-1][1] + 0.4
        g_end = nxt if nxt - g[-1][1] < 0.6 else g[-1][1] + 0.3
        toks = [_clean(w).upper() if vertical else _clean(w) for _, _, w in g]
        for wi, (s, _, _) in enumerate(g):
            e = g[wi + 1][0] if wi + 1 < len(g) else g_end
            txt = " ".join(
                (f"{{\\c&H{accent_bgr}&\\fscx112\\fscy112}}{t}{{\\r}}" if k == wi else t)
                for k, t in enumerate(toks))
            lines.append(f"Dialogue: 0,{_ts(s)},{_ts(e)},Cap,,0,0,0,,{txt}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n")
