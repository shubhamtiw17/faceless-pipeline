"""Sound design, 100% free: effects are synthesised with ffmpeg (no downloads, no keys).
Drop real recordings into assets/sfx/<name>.mp3 (gavel, cash, typing, crowd, heartbeat, impact, siren,
whoosh, riser) and they are used instead. Everything is mixed with numpy under the narration."""
import random, subprocess
from pathlib import Path
import numpy as np

SR = 48000
GEN = {  # name -> ffmpeg lavfi source
    "whoosh":    "anoisesrc=d=0.9:color=pink:a=1.0,highpass=f=500,lowpass=f=7000,afade=t=in:d=0.45:curve=exp,afade=t=out:st=0.45:d=0.45",
    "impact":    "aevalsrc='0.9*sin(2*PI*(38+70*exp(-7*t))*t)*exp(-2.6*t)+0.25*(random(0)-0.5)*exp(-18*t)':d=2.2",
    "riser":     "aevalsrc='0.35*(t/2.2)*sin(2*PI*(120+520*t*t/4.84)*t)+0.15*(t/2.2)*(random(0)-0.5)':d=2.2,highpass=f=150",
    "gavel":     "aevalsrc='0.9*sin(2*PI*190*t)*exp(-28*t)+0.5*sin(2*PI*620*t)*exp(-45*t)+0.9*gte(t,0.28)*sin(2*PI*190*(t-0.28))*exp(-28*(t-0.28))':d=0.9",
    "cash":      "aevalsrc='0.6*(random(0)-0.5)*exp(-60*t)+0.35*(sin(2*PI*2637*t)+sin(2*PI*3951*t))*gte(t,0.08)*exp(-5*(t-0.08))':d=1.1",
    "typing":    "aevalsrc='(random(0)-0.5)*1.4*lt(mod(t+0.03*sin(9*t),0.14),0.012)':d=2.4,highpass=f=1200",
    "crowd":     "anoisesrc=d=4:color=brown:a=0.5,lowpass=f=900,highpass=f=120,tremolo=f=2.5:d=0.6,afade=t=in:d=0.6,afade=t=out:st=3.2:d=0.8",
    "heartbeat": "aevalsrc='0.9*sin(2*PI*48*t)*exp(-22*mod(t,0.85))+0.6*gte(mod(t,0.85),0.22)*sin(2*PI*48*t)*exp(-22*(mod(t,0.85)-0.22))':d=3.4",
    "siren":     "aevalsrc='0.22*sin(2*PI*(700+250*sin(2*PI*0.9*t))*t)':d=3,lowpass=f=2500,afade=t=in:d=0.8,afade=t=out:st=2:d=1",
}
VOL = {"whoosh": 0.20, "impact": 0.30, "riser": 0.16, "gavel": 0.26, "cash": 0.22, "typing": 0.14,
       "crowd": 0.14, "heartbeat": 0.28, "siren": 0.10}
BEDS = {  # background drone by channel mood
    "dark": "aevalsrc='0.22*sin(2*PI*55*t)+0.16*sin(2*PI*82.41*t+sin(2*PI*0.07*t))+0.10*sin(2*PI*110.4*t)"
            "+0.05*sin(2*PI*164.8*t)*(0.5+0.5*sin(2*PI*0.05*t))':d={d},lowpass=f=900,tremolo=f=0.15:d=0.3",
    "luxury": "aevalsrc='0.14*sin(2*PI*110*t)+0.11*sin(2*PI*138.6*t+sin(2*PI*0.09*t))+0.10*sin(2*PI*164.8*t)"
              "+0.06*sin(2*PI*220*t)*(0.5+0.5*sin(2*PI*0.04*t))':d={d},lowpass=f=1800,tremolo=f=0.2:d=0.25",
}


def load(path, sr=SR):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def save(arr, path, sr=SR):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-",
                    "-ac", "2", str(path)], input=arr.astype(np.float32).tobytes(), check=True)


def _lavfi(src, out):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src, "-ar", str(SR), "-ac", "1", str(out)],
                   check=True)


class SoundDesign:
    def __init__(self, cache_dir="cache/sfx", custom_dir="assets/sfx"):
        self.cache = Path(cache_dir); self.cache.mkdir(parents=True, exist_ok=True)
        self.custom = Path(custom_dir)
        self._mem = {}

    def get(self, name):
        if name not in GEN:
            return None
        if name in self._mem:
            return self._mem[name]
        custom = sorted(self.custom.glob(f"{name}*.mp3")) + sorted(self.custom.glob(f"{name}*.wav"))
        if custom:
            arr = load(random.choice(custom))
        else:
            p = self.cache / f"{name}.wav"
            if not p.exists():
                _lavfi(GEN[name], p)
            arr = load(p)
        self._mem[name] = arr
        return arr

    def bed(self, mood, seconds, workdir):
        p = Path(workdir) / "bed.wav"
        _lavfi(BEDS.get(mood, BEDS["dark"]).format(d=round(seconds + 1, 2)), p)
        a = load(p)
        fade = int(SR * 2)
        a[:fade] *= np.linspace(0, 1, fade); a[-fade:] *= np.linspace(1, 0, fade)
        return a

    def mix(self, voice_path, events, mood, music_files, workdir, out, bed_level=0.06):
        """events: [(time_s, sfx_name)]. Writes stereo wav at out."""
        voice = load(voice_path)
        n = len(voice)
        mixb = voice.copy()
        bed = self.bed(mood, n / SR, workdir)[:n]
        if bed_level > 0:
            mixb[:len(bed)] += bed * (bed_level * 0.6 if music_files else bed_level)
        if music_files:
            m = load(random.choice(music_files))
            m = np.tile(m, int(np.ceil(n / max(len(m), 1))))[:n]
            m[-SR * 3:] *= np.linspace(1, 0, min(SR * 3, len(m)))
            mixb += m * 0.10
        for t, name in events:
            s = self.get(name)
            if s is None:
                continue
            i = int(max(t, 0) * SR)
            if i >= n:
                continue
            seg = s[: n - i] * VOL.get(name, 0.3)
            mixb[i:i + len(seg)] += seg
        peak = float(np.max(np.abs(mixb))) or 1.0
        if peak > 0.98:
            mixb *= 0.98 / peak
        save(mixb, out)
        return out
