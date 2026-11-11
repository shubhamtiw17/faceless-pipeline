"""Keeps the Instagram queue in a GitHub Release ("ig-queue") so it survives between runs.
(GitHub's Actions cache proved unreliable.) Only active on GitHub Actions; local runs use the folder."""
import os, subprocess
from pathlib import Path

TAG = "ig-queue"


def _gh(*args, check=True):
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=check)


def enabled():
    return bool(os.environ.get("GITHUB_ACTIONS") and os.environ.get("GH_TOKEN"))


def _ensure():
    if _gh("release", "view", TAG, check=False).returncode != 0:
        _gh("release", "create", TAG, "--title", "Instagram queue (automatic)", "--prerelease",
            "--notes", "Reels waiting to be posted. Managed by the pipeline; do not edit.")


def _assets():
    out = _gh("release", "view", TAG, "--json", "assets", "-q", ".assets[].name", check=False).stdout
    return [x for x in out.split() if x]


def pull(channel, qdir):
    if not enabled():
        return
    try:
        _ensure()
        prefix = f"{channel}__"
        names = [a for a in _assets() if a.startswith(prefix)]
        qdir.mkdir(parents=True, exist_ok=True)
        for a in names:
            dst = qdir / a[len(prefix):]
            if not dst.exists():
                _gh("release", "download", TAG, "-p", a, "-O", str(dst), "--clobber")
        print(f"[queue] restored {len([n for n in names if n.endswith('.json')])} queued Reel(s)")
    except Exception as e:  # noqa: BLE001
        print(f"[queue] restore failed: {e}")


def push(channel, qdir):
    if not enabled():
        return
    try:
        _ensure()
        prefix = f"{channel}__"
        remote = {a for a in _assets() if a.startswith(prefix)}
        local = {f"{prefix}{p.name}": p for p in Path(qdir).glob("*") if p.suffix in (".json", ".mp4")}
        import shutil, tempfile
        tmp = Path(tempfile.mkdtemp())
        for name, p in local.items():
            if name not in remote:
                cp = tmp / name
                shutil.copy(p, cp)
                _gh("release", "upload", TAG, str(cp), "--clobber")
        for name in remote - set(local):
            _gh("release", "delete-asset", TAG, name, "-y", check=False)
        print(f"[queue] saved {len([n for n in local if n.endswith('.json')])} queued Reel(s)")
    except Exception as e:  # noqa: BLE001
        print(f"[queue] save failed: {e}")
