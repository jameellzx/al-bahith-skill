"""No-repeat memory for al-bahith. Stores every page already put in a table.

  python seen.py check <page_id>            -> prints "seen" or "new"
  python seen.py add <mode> <json_file>     -> adds every page_id found in the file's rows/passed lists
  python seen.py add-id <mode> <page_id> [name]
  python seen.py count
"""
import json, sys, pathlib
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from paths import DATA, SEEN as FILE  # noqa: E402


def load():
    if FILE.exists():
        return json.loads(FILE.read_text(encoding="utf-8"))
    return {}


def save(d):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(FILE)


def all_ids():
    return set(load().keys())


def add(entries, mode):
    d = load()
    n = 0
    for pid, name in entries:
        if pid and pid not in d:
            d[pid] = {"name": name, "mode": mode, "date": date.today().isoformat()}
            n += 1
    save(d)
    return n


def _rows(obj):
    if isinstance(obj, list):
        return obj
    rows = []
    for k in ("rows", "passed", "check_these", "middle", "refs", "clients"):
        v = obj.get(k)
        if isinstance(v, list):
            rows += v
    return rows


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "count"
    if cmd == "check":
        print("seen" if sys.argv[2] in all_ids() else "new")
    elif cmd == "add":
        mode, f = sys.argv[2], sys.argv[3]
        rows = _rows(json.loads(pathlib.Path(f).read_text(encoding="utf-8")))
        print("added", add([(str(r.get("page_id")), r.get("page_name")) for r in rows], mode))
    elif cmd == "add-id":
        print("added", add([(sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")], sys.argv[2]))
    else:
        print(len(load()))
