"""Merge a run's data, sort pages into tables, and add them to the ONE Excel file (al-bahith).

  python write_xlsx.py --run run_dir --field "<field or all>" [--want 50]
  python write_xlsx.py --from-final run_dir/final.json [--field "..."]   (re-add a past run)

Reads from run_dir: candidates.json (adlib_scan), sites.json (site_check), shots/shots.json (shots),
ig.json (ig_profile, clients only, optional), scores.json (Claude's visual scores, see SKILL.md).
Writes run_dir/final.json and appends the rows to <data dir>/الباحث.xlsx (see paths.py; sheets: المراجع, عملائي,
شيك عليها, وسط). Existing rows stay; pages already in a sheet are not added twice; المراجع stays sorted by days.
"""
import argparse, json, pathlib, re
from datetime import date
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from paths import MASTER  # noqa: E402  (<data dir>/الباحث.xlsx)
DIAL = {"KW": "965", "SA": "966", "AE": "971", "QA": "974", "BH": "973", "OM": "968", "JO": "962", "EG": "20",
        "LB": "961", "IQ": "964", "US": "1", "GB": "44"}
VISUAL =["c2", "c3", "c4", "c5", "c6", "c7", "c8", "c10"]


def load(p, default):
    p = pathlib.Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def score_site(site, shot, sc):
    """Return (score 0-10 or None, note). c1 = mobile load < 3 s, c9 = pixel/GA, rest from Claude."""
    chk = site.get("check") or {}
    pts, avail, notes = 0, 0, []
    secs = shot.get("load_seconds")
    if secs is None:
        notes.append("سرعة الجوال غير معروفة")
    else:
        avail += 1
        pts += secs < 3
    avail += 1
    pts += bool(chk.get("meta_pixel") or chk.get("google_analytics") or shot.get("meta_pixel") or shot.get("google_analytics"))
    if not sc:
        return None, "لم يُقيَّم بصرياً"
    for c in VISUAL:
        if c in sc:
            avail += 1
            pts += bool(sc[c])
    score = round(pts / avail * 10) if avail else None
    if avail < 10 and score is not None:
        notes.append(f"الدرجة محسوبة من {avail} معايير")
    return score, "؛ ".join(notes)


def has_real_site(site, shot):
    if site.get("kind") != "site":
        return False
    chk = site.get("check") or {}
    if chk.get("loads") is False:
        return False
    if shot and shot.get("browser_loads") is False:
        return False
    if chk.get("loads") is None and not shot:
        return False
    return True


def joined(*lists):
    out = []
    for l in lists:
        for x in l or []:
            if x and x not in out:
                out.append(x)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run")
    ap.add_argument("--field", default="all")
    ap.add_argument("--want", type=int, default=0)
    ap.add_argument("--master", default=str(MASTER))
    ap.add_argument("--no-site", action="store_true", help="clients: keep only businesses with no working website")
    ap.add_argument("--from-final", help="append an existing final.json to the master file (no recompute)")
    a = ap.parse_args()
    if a.from_final:
        final = load(a.from_final, None)
        if a.field != "all":
            final["field"] = a.field
        print(json.dumps(append_to_master(final, pathlib.Path(a.master)), ensure_ascii=False))
        return
    run = pathlib.Path(a.run)
    cand = load(run / "candidates.json", None)
    sites = load(run / "sites.json", {})
    shots = load(run / "shots" / "shots.json", {})
    ig = load(run / "ig.json", {})
    scores = load(run / "scores.json", {})
    for part in sorted(run.glob("scores_part*.json")):
        scores.update(load(part, {}))
    mode, cc = cand["mode"], cand["country"]
    want = a.want or (20 if mode == "refs" else 50)

    rows, check_these, middle, dropped = [], [], [], []
    for p in cand["passed"]:
        pid = p["page_id"]
        site = sites.get(pid, {})
        shot = shots.get(pid, {})
        sc = scores.get(pid)
        real = has_real_site(site, shot)
        url = (site.get("check") or {}).get("final_url") or site.get("url")
        score, note = score_site(site, shot, sc) if real else (None, "")
        problems = (sc or {}).get("problems") or []
        secs = shot.get("load_seconds") if real else None
        if secs is not None and secs >= 3:
            problems = [f"الموقع ياخذ {secs} ثانية يفتح على الجوال"] + [
                x for x in problems if "ثانية" not in x and "بطيء" not in x]
        base = {"page_id": pid, "page_name": p["page_name"], "ad_library_url": p["ad_library_url"],
                "load_seconds": secs,
                "days_running": p.get("days_running"), "oldest_start": p.get("oldest_start"),
                "active_ads": p.get("active_ads"), "site_url": url if real else None, "site_kind": site.get("kind"),
                "score": score, "score_note": note, "problems": problems, "keywords": p.get("keywords")}
        if mode == "refs":
            if real and score is not None and score >= 7:
                rows.append(base)
            else:
                dropped.append((p["page_name"], "no site" if not real else f"score {score}"))
            continue
        igd = ig.get(p.get("ig_username") or "", {})
        chk = site.get("check") or {}
        base.update({
            "ig_username": p.get("ig_username"), "ig_url": p.get("ig_url"),
            "followers": p.get("ig_followers"), "has_site": real,
            "whatsapp": joined(igd.get("whatsapp"), p.get("whatsapp_from_ads"), chk.get("whatsapp")),
            "emails": joined(igd.get("emails"), chk.get("emails")),
            "manager_countries": p.get("manager_countries"), "ig_bio": igd.get("bio"),
            "why_strong": (sc or {}).get("why_strong"),
        })
        code = DIAL.get(cc)
        if code and base["whatsapp"] and not any(n.startswith(code) for n in base["whatsapp"]):
            dropped.append((p["page_name"], "phone from another country: " + ", ".join(base["whatsapp"])))
            continue
        if not real:
            base["problems"] =["ما عنده موقع" + (" (الرابط واتساب/انستقرام بس)" if site.get("kind") in ("whatsapp", "social", "linkhub") else "")]
            rows.append(base)
        elif score is None:
            middle.append({**base, "score_note": "لم يُقيَّم"})
        elif score <= 4:
            rows.append(base)
        elif score <= 6:
            middle.append(base)
        else:
            check_these.append(base)

    if mode == "refs":
        rows.sort(key=lambda r: -(r["days_running"] or 0))
    elif a.no_site:
        # user rule: "no website" runs keep ONLY businesses without a working website; nothing goes to وسط / شيك عليها
        dropped += [(r["page_name"], "has website") for r in rows + middle + check_these if r.get("has_site")]
        rows = [r for r in rows if not r.get("has_site")]
        middle, check_these = [], []
    rows = rows[:want]
    final = {"mode": mode, "country": cc, "field": a.field, "rows": rows, "check_these": check_these,
             "middle": middle, "stats": {**cand["stats"], "rows": len(rows), "check_these": len(check_these),
                                         "middle": len(middle), "dropped_after_site": len(dropped)},
             "dropped": [{"page_name": n, "why": w} for n, w in dropped]}
    (run / "final.json").write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")

    res = append_to_master(final, pathlib.Path(a.master))
    print(json.dumps({**res, **final["stats"]}, ensure_ascii=False))


# ---------- the one master workbook ----------
REF_HEADS = ["الاسم", "رابط الموقع", "مدة الإعلان (أيام)", "بداية الإعلان", "عدد الإعلانات النشطة", "درجة الموقع",
             "سرعة الجوال (ثانية)", "ملاحظة", "رابط Ad Library", "الدولة", "المجال", "تاريخ البحث"]
CLI_HEADS = ["الاسم", "رابط انستقرام", "عدد المتابعين", "عنده موقع؟", "الموقع", "واتساب", "إيميل",
             "وين لقيته (Ad Library)", "درجة الموقع", "أكثر 3 مشاكل", "عدد الإعلانات", "مدة الإعلان (أيام)",
             "دولة إدارة الصفحة", "كلمة البحث", "الدولة", "المجال", "تاريخ البحث"]
CHK_HEADS = ["الاسم", "الموقع", "الدرجة", "ليش شفته قوي", "مدة الإعلان (أيام)", "رابط Ad Library",
             "الدولة", "المجال", "تاريخ البحث"]
SHEETS = [("المراجع", REF_HEADS), ("عملائي", CLI_HEADS), ("شيك عليها", CHK_HEADS), ("وسط", CLI_HEADS)]


def _ref_row(r, tail):
    return [r["page_name"], r["site_url"], r["days_running"], r["oldest_start"], r["active_ads"], r["score"],
            r.get("load_seconds"), r["score_note"], r["ad_library_url"]] + tail


def _cli_row(r, tail):
    return [r["page_name"], r["ig_url"], r["followers"], "نعم" if r["has_site"] else "لا", r["site_url"],
            " / ".join(r["whatsapp"]) or "غير متوفر", " / ".join(r["emails"]) or "غير متوفر",
            r["ad_library_url"], r["score"], " | ".join(r["problems"][:3]), r["active_ads"], r["days_running"],
            r.get("manager_countries") or "غير معروف", ", ".join(r.get("keywords") or [])] + tail


def _chk_row(r, tail):
    return [r["page_name"], r["site_url"], r["score"], r.get("why_strong") or "", r["days_running"],
            r["ad_library_url"]] + tail


def append_to_master(final, master):
    """Append a run's rows to the single workbook. Keeps every existing row (and any extra columns the user
    added), skips pages already in that sheet, re-sorts المراجع by days running (longest first)."""
    tail = [final["country"], final.get("field") or "all", date.today().isoformat()]
    new = {"المراجع": [], "عملائي": [], "شيك عليها": [], "وسط": []}
    if final["mode"] == "refs":
        new["المراجع"] = [_ref_row(r, tail) for r in final["rows"]]
    else:
        new["عملائي"] = [_cli_row(r, tail) for r in final["rows"]]
        new["شيك عليها"] = [_chk_row(r, tail) for r in final["check_these"]]
        new["وسط"] = [_cli_row(r, tail) for r in final["middle"]]

    old = {}
    if master.exists():
        wb0 = load_workbook(master)
        for ws in wb0.worksheets:
            vals = list(ws.iter_rows(values_only=True))
            old[ws.title] = ([list(v) for v in vals[1:] if any(x not in (None, "") for x in v)],
                             list(vals[0]) if vals else None)

    wb = Workbook()
    wb.remove(wb.active)
    hfont, hfill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F4E78")
    added = {}
    for title, heads in SHEETS:
        rows, oldheads = old.get(title, ([], None))
        heads = oldheads if oldheads and len(oldheads) >= len(heads) else heads
        key_col = next((i for i, h in enumerate(heads) if h and "Ad Library" in str(h)), None)
        have = {str(r[key_col]) for r in rows if key_col is not None and len(r) > key_col}
        fresh = [r for r in new[title] if key_col is None or str(r[key_col]) not in have]
        added[title] = len(fresh)
        rows = rows + fresh
        if title == "المراجع":
            rows.sort(key=lambda r: -(r[2] if isinstance(r[2], (int, float)) else 0))
        ws = wb.create_sheet(title)
        ws.sheet_view.rightToLeft = True
        ws.append(heads)
        for c in ws[1]:
            c.font, c.fill, c.alignment = hfont, hfill, Alignment(horizontal="center", wrap_text=True)
        for r in rows:
            ws.append(["" if v is None else v for v in r])
        for i, h in enumerate(heads, 1):
            cells = [str(r[i - 1]) for r in rows if len(r) >= i and r[i - 1] is not None]
            ws.column_dimensions[get_column_letter(i)].width = max([len(str(h or ""))] + [min(len(c), 60) for c in cells]) + 2
            for row in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                v = row[0].value
                if isinstance(v, str) and v.startswith("http"):
                    row[0].hyperlink, row[0].font = v, Font(color="0563C1", underline="single")
        ws.freeze_panes = "A2"
    master.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(master)
        saved = master
    except PermissionError:  # the file is open in Excel
        saved = master.with_name(master.stem + "_جديد.xlsx")
        wb.save(saved)
        print(f"WARN: {master.name} is open in Excel; saved to {saved.name}. Close Excel, then rerun with --from-final to merge.")
    return {"xlsx": str(saved), "added": added}


if __name__ == "__main__":
    main()
