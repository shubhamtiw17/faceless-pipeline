"""Fact-check every script before anything is rendered.
1st choice: Gemini with live Google Search. Backup: Groq reviewing with what it knows (marked 'unverified').
Wrong claims get rewritten or removed; a story that can't be supported is rejected (a new one is written)."""
import json
from .llm import generate_json, search_json

ASK = """You are the fact-checker of a true-story YouTube channel. Real people and companies are named, so
every factual claim must be supported by public reporting (court records, government releases, major news).
{search_hint}

<<<SOURCE
{source}
SOURCE>>>

Story title: {title}
Sources the writer cited: {sources}

Numbered narration lines:
{lines}

For EVERY line with a factual claim (names, years, amounts, charges, verdicts, methods), check it AGAINST THE SOURCE.
- If a detail contradicts the SOURCE, rewrite the line with the SOURCE's detail, same length and tone.
- If a detail is NOT in the SOURCE, rewrite the line without it (keep the storytelling).
- Opinions, questions and hooks without facts are fine as they are.
- verdict "reject" only if the core story is not what the SOURCE describes.

Return ONLY JSON:
{{"verdict": "ok" | "fixed" | "reject",
  "fixes": [{{"line": <number>, "text": "corrected line", "why": "short reason"}}],
  "sources": ["specific sources you relied on: outlet, title, year"]}}"""


def _lines(beats):
    return "\n".join(f"{i}. {b['text']}" for i, b in enumerate(beats))


def check(beats, title, sources, llm_cfg, source_text="", chunk=60):
    """Mutates beats in place with corrections. Returns (verdict, n_fixes, sources, method).
    Long scripts are checked in chunks so each request stays small (free-tier limits)."""
    if len(beats) > chunk:
        verdicts, fixes, srcs, method = [], 0, [], None
        for i in range(0, len(beats), chunk):
            v, n, s2, method = check(beats[i:i + chunk], title, sources, llm_cfg, source_text, chunk)
            verdicts.append(v); fixes += n; srcs += s2
        rej = verdicts.count("reject") > len(verdicts) / 2
        return ("reject" if rej else "fixed" if fixes else "ok"), fixes, srcs, method
    payload = dict(title=title, sources="; ".join(map(str, sources or [])) or "none", lines=_lines(beats),
                   source=source_text[:10000] or "(no source text - use Google Search)")
    if source_text:   # grounded: compare against the downloaded article (works with any model)
        res = generate_json(ASK.format(search_hint="Judge ONLY against the SOURCE text below.", **payload), llm_cfg)
        method = "source-grounded"
    else:
        res = search_json(ASK.format(search_hint="Use Google Search to verify each claim.", **payload), llm_cfg)
        method = "google-search"
        if not isinstance(res, dict):
            method = "model-knowledge (unverified)"
            res = generate_json(ASK.format(search_hint="Be conservative: soften anything uncertain.", **payload),
                                llm_cfg)
    fixes = 0
    for f in res.get("fixes", []) or []:
        try:
            i, txt = int(f.get("line")), str(f.get("text", "")).strip()
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(beats) and txt and txt != beats[i]["text"]:
            print(f"[fact] line {i}: {beats[i]['text'][:60]!r} -> {txt[:60]!r} ({str(f.get('why', ''))[:60]})")
            beats[i]["text"] = txt
            fixes += 1
    verdict = str(res.get("verdict", "ok")).lower()
    return verdict, fixes, res.get("sources") or [], method


def check_script(data, llm_cfg):
    """Checks the long chapters + Shorts series (long days) or the standalone Short. False = reject story."""
    report, src = {}, []
    st = data.get("source_text", "")
    groups = []
    if data.get("scenes"):
        groups.append(("long", [b for sc in data["scenes"] for b in sc["beats"]]))
        for k, p in enumerate(data.get("parts") or []):
            groups.append((f"part{k + 1}", p["beats"]))
    else:
        groups.append(("short", data["short"]["beats"]))
    for name, beats in groups:
        v, n, s2, how = check(beats, data.get("title", ""), data.get("sources"), llm_cfg, st)
        report[name] = {"verdict": v, "fixes": n, "method": how}
        src += s2
        if v == "reject" and name in ("long", "short"):
            data["factcheck"] = report
            return False
    if src and not st:  # cite what the checker actually used (search mode)
        data["sources"] = list(dict.fromkeys(map(str, src)))[:8]
    data["factcheck"] = report
    print(f"[fact] {json.dumps(report)}")
    return True
