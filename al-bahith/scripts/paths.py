"""Where al-bahith keeps its data (Excel file, no-repeat memory, Instagram session, run folders).

Order: env AL_BAHITH_DATA -> "data_dir" in <skill>/config.json -> ~/al-bahith
"""
import json, os, pathlib

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent


def data_dir():
    env = os.environ.get("AL_BAHITH_DATA")
    if env:
        return pathlib.Path(env).expanduser()
    cfg = SKILL_DIR / "config.json"
    if cfg.exists():
        try:
            d = json.loads(cfg.read_text(encoding="utf-8")).get("data_dir")
            if d:
                return pathlib.Path(d).expanduser()
        except Exception:
            pass
    return pathlib.Path.home() / "al-bahith"


DATA = data_dir()
SEEN = DATA / "seen.json"
IG_STATE = DATA / "ig_state"
MASTER = DATA / "الباحث.xlsx"
RUNS = DATA / "runs"

if __name__ == "__main__":
    print(DATA)
