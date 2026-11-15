"""Field check by eye before the Excel step (al-bahith).

  python review.py list RUN_DIR                 -> one line per lead: id | name | category | bio (from ig.json)
  python review.py drop RUN_DIR id1,id2 --why "bakery, not perfume"
                                                -> moves those leads from passed to rejected in candidates.json

ids are ig_username (Instagram leads) or page_id (Ad Library leads).
"""
import argparse, json, pathlib, sys


def load(run):
    cand = json.loads((run / "candidates.json").read_text(encoding="utf-8"))
    igf = run / "ig.json"
    ig = json.loads(igf.read_text(encoding="utf-8")) if igf.exists() else {}
    return cand, ig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "drop"])
    ap.add_argument("run")
    ap.add_argument("ids", nargs="?", default="")
    ap.add_argument("--why", default="not in the field (review)")
    a = ap.parse_args()
    run = pathlib.Path(a.run)
    cand, ig = load(run)
    if a.cmd == "list":
        for p in cand["passed"]:
            i = ig.get(p.get("ig_username") or "", {})
            bio = (i.get("bio") or "").replace("\n", " ")[:120]
            cat = i.get("category") or p.get("category") or ", ".join(p.get("categories") or [])
            print(f"{p.get('ig_username') or p['page_id']} | {p['page_name']} | {cat or '-'} | {bio or '-'}")
        print(f"{len(cand['passed'])} leads")
        return
    ids = {x.strip().lower() for x in a.ids.split(",") if x.strip()}
    keep, moved = [], []
    for p in cand["passed"]:
        key = {(p.get("ig_username") or "").lower(), str(p["page_id"]).lower()}
        if key & ids:
            moved.append(p)
            cand.setdefault("rejected_sample", []).append(
                {"handle": p.get("ig_username"), "page_name": p["page_name"], "why": [a.why]})
        else:
            keep.append(p)
    cand["passed"] = keep
    cand.setdefault("stats", {})["passed"] = len(keep)
    (run / "candidates.json").write_text(json.dumps(cand, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"dropped {len(moved)}: {', '.join(p['page_name'] for p in moved)} | {len(keep)} leads left")
    missing = ids - {(p.get('ig_username') or '').lower() for p in moved} - {str(p['page_id']).lower() for p in moved}
    if missing:
        print("not found:", ", ".join(sorted(missing)), file=sys.stderr)


if __name__ == "__main__":
    main()
