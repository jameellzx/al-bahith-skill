"""Instagram as a lead source for al-bahith (clients mode). Uses the user's saved Instagram session.

Phase 1 (phone mode, like the iPhone app's web view): search keywords and hashtags, collect every account that
posted in the results, plus every @account tagged in their captions (shops that pay influencers).
Phase 2 (paced): read each new account's profile, apply the clients rules, write the same files adlib_scan +
ig_profile write, so site_check.py / shots.py / write_xlsx.py run unchanged.

  python ig_search.py --country KW --keywords "perfume kuwait|عطور الكويت" [--hashtags "عطور_الكويت|perfumekuwait"]
                      --out RUN_DIR [--scrolls 4] [--cap 80] [--min-wait 5] [--max-wait 10]

Writes RUN_DIR/candidates.json (passed = leads, like adlib_scan) and RUN_DIR/ig.json (bio contacts).
Exit 4 on login wall / rate limit (progress saved: rerun the same command to continue).
"""
import argparse, asyncio, json, random, re, sys, time, pathlib
from datetime import datetime
from urllib.parse import quote

from patchright.async_api import async_playwright

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from paths import IG_STATE, MASTER, RUNS  # noqa: E402
import seen as seen_store  # noqa: E402
from ig_profile import profile_object, extract, contact_card, merge_card  # noqa: E402
from adlib_scan import COUNTRY_HINTS, COUNTRY_NAMES  # noqa: E402

PHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/18.1 Mobile/15E148 Safari/604.1")
DIAL = {"KW": "965", "SA": "966", "AE": "971", "QA": "974", "BH": "973", "OM": "968", "JO": "962", "EG": "20"}
MIN_F, MAX_F = 1000, 70000
# categories that mean a person/creator, not a shop
CREATOR = re.compile(r"creator|blogger|public figure|influencer|personal blog|artist|actor|musician|athlete|"
                     r"journalist|video creator|gamer|comedian|photographer|entrepreneur|coach|education|news", re.I)
# words that mean a shop / service even when Instagram's category says "creator"
SHOP = re.compile(r"shop|store|boutique|perfume|parfum|salon|clinic|cafe|restaurant|bakery|abaya|order|delivery|"
                  r"متجر|محل|عطور|عطر|بخور|صالون|عيادة|مطعم|كافيه|حلويات|عبايات|للطلب|طلبات|توصيل|واتساب", re.I)
MENTION = re.compile(r"@([A-Za-z0-9._]{3,30})")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def walk_media(o, found, source):
    """Collect post authors and caption @mentions from any Instagram JSON."""
    stack = [o]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            u = x.get("user")
            if "code" in x and isinstance(u, dict) and u.get("username"):
                code = x["code"]
                cap = x.get("caption")
                text = cap.get("text") if isinstance(cap, dict) else ""
                rec = found.setdefault(u["username"].lower(), {"via": [], "post": f"https://www.instagram.com/p/{code}/",
                                                               "verified": u.get("is_verified")})
                if source not in rec["via"]:
                    rec["via"].append(source)
                for m in MENTION.findall(text or ""):
                    m = m.lower().rstrip(".")
                    if m != u["username"].lower():
                        r2 = found.setdefault(m, {"via": [], "post": f"https://www.instagram.com/p/{code}/", "verified": None})
                        tag = f"{source} (tagged by @{u['username']})"
                        if tag not in r2["via"]:
                            r2["via"].append(tag)
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)


async def phase_search(keywords, hashtags, scrolls):
    found = {}
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            str(IG_STATE), headless=True, user_agent=PHONE_UA, viewport={"width": 390, "height": 844},
            device_scale_factor=3, is_mobile=True, has_touch=True, locale="en-US")
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        bodies = []

        async def on_resp(r):
            if "instagram.com" in r.url and ("graphql" in r.url or "/api/v1/" in r.url):
                try:
                    bodies.append(await r.text())
                except Exception:
                    pass
        page.on("response", on_resp)
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        if "accounts/login" in page.url or "/challenge" in page.url:
            await ctx.close()
            print("LOGIN_WALL: run ig_profile.py --login"); sys.exit(4)
        targets = [(f"https://www.instagram.com/explore/search/keyword/?q={quote(k)}", f"IG search: {k}") for k in keywords]
        targets += [(f"https://www.instagram.com/explore/tags/{quote(h.lstrip('#'))}/", f"IG #{h.lstrip('#')}") for h in hashtags]
        for url, source in targets:
            bodies.clear()
            n0 = len(found)
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)
            for _ in range(scrolls):
                await page.mouse.wheel(0, 2500)
                await page.wait_for_timeout(random.uniform(2.0, 3.5) * 1000)
            html = await page.content()
            for b in bodies + [html]:
                for line in b.splitlines():
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            walk_media(json.loads(line), found, source)
                        except Exception:
                            pass
                # embedded JSON in the HTML
                dec = json.JSONDecoder()
                for m in re.finditer(r'\{"code":"', b):
                    try:
                        obj, _ = dec.raw_decode(b, m.start())
                        walk_media(obj, found, source)
                    except Exception:
                        pass
            log(f"{source}: +{len(found) - n0} accounts (total {len(found)})")
            await page.wait_for_timeout(random.uniform(4, 8) * 1000)
        await ctx.close()
    return found


def known_handles():
    """Handles already shown: seen.json (ig:<handle>) + Instagram links already in the Excel file."""
    ids = seen_store.all_ids()
    hs = {i[3:] for i in ids if i.startswith("ig:")}
    # accounts already read and rejected in earlier Instagram runs (don't spend profile reads on them again)
    for f in RUNS.glob("*/candidates.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("source") == "instagram":
                hs |= {r["handle"] for r in d.get("rejected_sample", []) if r.get("handle")}
        except Exception:
            pass
    if MASTER.exists():
        try:
            from openpyxl import load_workbook
            wb = load_workbook(MASTER, read_only=True)
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    for v in row:
                        if isinstance(v, str) and "instagram.com/" in v:
                            hs.add(v.rstrip("/").split("/")[-1].lower())
        except Exception:
            pass
    return hs


def judge(user, info, cc):
    """Return list of fail reasons (empty = lead)."""
    why = []
    f = user.get("follower_count")
    if f is None or f < MIN_F or f > MAX_F:
        why.append(f"followers {f} outside {MIN_F}-{MAX_F}")
    if user.get("is_private"):
        why.append("private")
    cat = user.get("category") or ""
    text = f"{user.get('username', '')} {user.get('full_name') or ''} {info.get('bio') or ''} {user.get('city_name') or ''}".lower()
    shopish = bool(SHOP.search(text)) or bool(info.get("whatsapp"))
    if (CREATOR.search(cat) and not shopish) or (not user.get("is_business") and not cat and not shopish):
        why.append(f"not a business ({cat or 'personal'})")
    code = DIAL.get(cc)
    phones = info.get("whatsapp") or []
    local = bool(code and any(p.startswith(code) for p in phones)) or any(re.search(h, text) for h in COUNTRY_HINTS.get(cc, []))
    foreign = bool(code and phones and not any(p.startswith(code) for p in phones))
    if not foreign:
        for other, hints in COUNTRY_HINTS.items():
            if other != cc and any(re.search(h, text) for h in hints) and not local:
                foreign = True
                break
    if foreign:
        why.append("from another country")
    elif not local:
        why.append(f"no sign it is in {COUNTRY_NAMES.get(cc, cc)}")
    return why


async def phase_profiles(handles, found, cc, cap, wmin, wmax, out, want=0, no_site=False):
    cand_f, ig_f = out / "candidates.json", out / "ig.json"
    state = json.loads(cand_f.read_text(encoding="utf-8")) if cand_f.exists() else None
    ig = json.loads(ig_f.read_text(encoding="utf-8")) if ig_f.exists() else {}
    passed = state["passed"] if state else []
    rejected = state.get("rejected_sample", []) if state else []
    if no_site and passed:
        # leads kept by an earlier run of this folder without --no-site: drop the ones with a working website
        keep = []
        for p in passed:
            site = await asyncio.to_thread(working_site, p, ig.get(p["ig_username"], {}))
            if site:
                rejected.append({"handle": p["ig_username"], "page_name": p["page_name"], "why": [f"has website {site}"]})
            else:
                keep.append(p)
        log(f"--no-site: {len(passed) - len(keep)} earlier leads have a website and were dropped, {len(keep)} kept")
        passed = keep
    done = {p["ig_username"] for p in passed} | {r["handle"] for r in rejected if "handle" in r} | set(ig)
    todo = [h for h in handles if h not in done][:cap]
    log(f"phase 2: {len(todo)} profiles to read")
    status = "OK"
    card_on, card_fails, net_fails = True, 0, 0
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(str(IG_STATE), headless=True)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        for i, h in enumerate(todo, 1):
            try:
                resp = await page.goto(f"https://www.instagram.com/{h}/", wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(2500)
                html = await page.content()
            except Exception as e:
                # network/load problem: not a rejection, the account is read again next run
                net_fails += 1
                log(f"  load failed for {h}: {repr(e)[:80]}")
                if net_fails >= 5:
                    status = "NETWORK"; break
                await page.wait_for_timeout(10000)
                continue
            net_fails = 0
            if "accounts/login" in page.url or "/challenge" in page.url:
                status = "LOGIN_WALL"; break
            if (resp and resp.status == 429) or "Please wait a few minutes" in html:
                status = "RATE_LIMIT"; break
            user = profile_object(html, h)
            if not user:
                rejected.append({"handle": h, "page_name": h, "why": ["no profile data"]})
                continue
            info = extract(user, cc)
            f = user.get("follower_count") or 0
            if card_on and MIN_F <= f <= MAX_F and not user.get("is_private"):
                await page.wait_for_timeout(random.uniform(1.5, 3) * 1000)
                card = await contact_card(ctx, user.get("pk") or user.get("id"))
                if card is None:
                    card_fails += 1
                    if card_fails >= 3:
                        card_on = False
                        log("contact button data refused 3 times in a row: skipping it for the rest of this run")
                else:
                    card_fails = 0
                    info = merge_card(info, card)
            ig[h] = info
            why = judge(user, info, cc)
            if why:
                rejected.append({"handle": h, "page_name": user.get("full_name") or h, "why": why})
            else:
                rec = found.get(h, {})
                if no_site:
                    site = await asyncio.to_thread(working_site, {"website_candidates": info["links"]}, info)
                    if site:
                        rejected.append({"handle": h, "page_name": user.get("full_name") or h, "why": [f"has website {site}"]})
                        save(out, cc, passed, rejected, ig, found)
                        await page.wait_for_timeout(random.uniform(wmin, wmax) * 1000)
                        continue
                passed.append({
                    "page_id": f"ig:{h}", "page_name": user.get("full_name") or h,
                    "ig_username": h, "ig_url": f"https://www.instagram.com/{h}/", "ig_followers": user.get("follower_count"),
                    "ad_library_url": rec.get("post") or f"https://www.instagram.com/{h}/",
                    "active_ads": None, "days_running": None, "oldest_start": None,
                    "website_candidates": [l for l in info["links"]], "caption_domains": [],
                    "link_kinds": [], "whatsapp_from_ads": [], "manager_countries": None,
                    "keywords": rec.get("via") or [], "source": "instagram", "category": user.get("category"),
                })
            if i % 10 == 0:
                log(f"  read {i}/{len(todo)}, leads {len(passed)}")
            save(out, cc, passed, rejected, ig, found)
            if want and len(passed) >= want:
                log(f"reached {want} leads, stopping")
                break
            await page.wait_for_timeout(random.uniform(wmin, wmax) * 1000)
        await ctx.close()
    save(out, cc, passed, rejected, ig, found)
    return status, passed, rejected


def working_site(lead, info):
    """URL of a website that really loads (bio link / contact data), or None. Link hubs, WhatsApp and
    Instagram links are not websites. Used by --no-site."""
    from site_check import pick_site, check
    pick = pick_site(lead, info)
    if pick["kind"] != "site":
        return None
    r = check(pick["url"], False)
    return (r["final_url"] or pick["url"]) if r["loads"] is not False and r["kind"] == "site" else None


def save(out, cc, passed, rejected, ig, found):
    res = {"mode": "clients", "country": cc, "source": "instagram", "scanned_at": datetime.now().isoformat(timespec="seconds"),
           "stats": {"pages_found": len(found), "skipped_seen": 0, "checked": len(passed) + len(rejected),
                     "passed": len(passed), "detail_errors": 0},
           "passed": passed, "rejected_sample": rejected}
    (out / "candidates.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "ig.json").write_text(json.dumps(ig, ensure_ascii=False, indent=1), encoding="utf-8")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--keywords", default="")
    ap.add_argument("--hashtags", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scrolls", type=int, default=4)
    ap.add_argument("--cap", type=int, default=80, help="max profiles to read this run")
    ap.add_argument("--want", type=int, default=0, help="stop after this many leads pass (0 = read up to --cap)")
    ap.add_argument("--no-site", action="store_true", help="only businesses with NO working website (skip any with one)")
    ap.add_argument("--min-wait", type=float, default=5)
    ap.add_argument("--max-wait", type=float, default=10)
    a = ap.parse_args()
    cc = a.country.upper()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    kws = [k.strip() for k in a.keywords.split("|") if k.strip()]
    tags = [t.strip() for t in a.hashtags.split("|") if t.strip()]
    found_f = out / "ig_found.json"
    if found_f.exists():
        found = json.loads(found_f.read_text(encoding="utf-8"))
        log(f"phase 1 skipped: {len(found)} accounts already found (delete ig_found.json to search again)")
    else:
        found = await phase_search(kws, tags, a.scrolls)
        found_f.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
    known = known_handles()
    # tagged shops first (they pay influencers), then the rest
    handles = sorted((h for h in found if h not in known), key=lambda h: (not any("tagged" in v for v in found[h]["via"]),
                                                                         bool(found[h].get("verified"))))
    log(f"{len(found)} accounts found, {len(found) - len(handles)} already known, {len(handles)} new")
    status, passed, rejected = await phase_profiles(handles, found, cc, a.cap, a.min_wait, a.max_wait, out, a.want,
                                                    a.no_site)
    print(json.dumps({"status": status, "found": len(found), "new": len(handles), "leads": len(passed),
                      "rejected": len(rejected)}))
    if status != "OK":
        sys.exit(4)


if __name__ == "__main__":
    asyncio.run(main())
