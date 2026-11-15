"""Meta Ad Library scanner for al-bahith (الباحث).

Stage A: keyword searches (active ads, one country) -> unique pages.
Stage B: for each new page, open its Ad Library page view -> active ad count,
         oldest active ad start date, Instagram handle + followers, manager countries.
Then applies the mode rules and writes candidates JSON.

Usage:
  python adlib_scan.py --mode refs|clients --country US --keywords "kw1|kw2" --out run_dir
         [--want 20] [--scrolls 4] [--workers 4] [--max-pages 200] [--no-seen]
"""
import argparse, asyncio, json, re, sys, time, pathlib
from datetime import datetime, timezone
from urllib.parse import quote, urlparse, parse_qs

from patchright.async_api import async_playwright

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import seen as seen_store  # noqa: E402

SEARCH_URL = ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
              "&country={cc}&q={q}&search_type=keyword_unordered&media_type=all")
PAGE_URL = ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
            "&country={cc}&view_all_page_id={pid}&search_type=page&media_type=all")

COUNTRY_NAMES = {"US": "United States", "KW": "Kuwait", "SA": "Saudi Arabia", "AE": "United Arab Emirates",
                 "QA": "Qatar", "BH": "Bahrain", "OM": "Oman", "GB": "United Kingdom", "JO": "Jordan",
                 "EG": "Egypt", "LB": "Lebanon", "IQ": "Iraq"}

COUNTRY_HINTS = {  # regexes on page name + Instagram handle
    "KW": [r"kuwait", r"\bkw\b", r"[._]kw\b", r"q8", r"الكويت"],
    "AE": [r"dubai", r"\buae\b", r"[._]uae\b", r"abu ?dhabi", r"sharjah", r"\bae\b", r"دبي", r"الامارات", r"الإمارات"],
    "SA": [r"\bksa\b", r"[._]ksa\b", r"riyadh", r"jeddah", r"saudi", r"\bsa\b", r"الرياض", r"جدة", r"السعودية"],
    "QA": [r"qatar", r"doha", r"[._]qa\b", r"\bqa\b", r"قطر", r"الدوحة"],
    "BH": [r"bahrain", r"[._]bh\b", r"\bbh\b", r"البحرين"],
    "OM": [r"\boman\b", r"muscat", r"[._]om\b", r"عمان", r"مسقط"],
    "EG": [r"egypt", r"cairo", r"مصر", r"القاهرة"],
}

RULES = {
    "refs":    {"min_ads": 91, "max_ads": None, "min_days": 90},
    "clients": {"min_ads": 1,  "max_ads": 14,  "min_days": 7, "min_f": 1000, "max_f": 70000},
}

SOCIAL = ("facebook.com", "fb.com", "fb.me", "instagram.com", "m.me", "messenger.com")
WA = ("wa.me", "whatsapp.com", "wa.link")
LINKHUBS = ("linktr.ee", "linkin.bio", "beacons.ai", "bio.link", "taplink", "lnk.bio", "campsite.bio", "linkbio",
            "reachlnk", "reach.link", "iwtsp.com", "solo.to", "allmylinks", "hoo.be", "msha.ke", "linkr.bio", "flow.page")

NOW = time.time()


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


# ---------- parsing helpers ----------
def iter_ads(obj):
    """Yield every dict that looks like an ad (has ad_archive_id)."""
    stack = [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            if "ad_archive_id" in o and "page_id" in o:
                yield o
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)


def json_chunks(text):
    """Parse every JSON document in a (possibly multi-line) GraphQL response."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("for (;;);"):
            line = line[9:]
        if not line.startswith("{"):
            continue
        try:
            yield json.loads(line)
        except Exception:
            continue


def html_connections(html):
    """Decode every embedded search_results_connection object in page HTML."""
    dec = json.JSONDecoder()
    key = '"search_results_connection":'
    i = 0
    while True:
        i = html.find(key, i)
        if i < 0:
            return
        try:
            obj, _ = dec.raw_decode(html, i + len(key))
            yield obj
        except Exception:
            pass
        i += len(key)


def classify_link(url):
    if not url:
        return None
    try:
        host = urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return None
    if not host:
        return None
    if any(h in host for h in WA):
        return "whatsapp"
    if any(host == s or host.endswith("." + s) for s in SOCIAL):
        return "social"
    if any(h in host for h in LINKHUBS):
        return "linkhub"
    return "site"


def wa_number(url):
    if not url:
        return None
    u = urlparse(url)
    if "wa.me" in u.netloc:
        num = u.path.strip("/").split("/")[0]
    else:
        num = (parse_qs(u.query).get("phone") or [""])[0]
    num = re.sub(r"\D", "", num or "")
    return num or None


def add_ad(pages, ad):
    pid = str(ad.get("page_id"))
    snap = ad.get("snapshot") or {}
    p = pages.setdefault(pid, {
        "page_id": pid, "page_name": ad.get("page_name") or snap.get("page_name"),
        "fb_url": snap.get("page_profile_uri"), "fb_likes": snap.get("page_like_count"),
        "categories": snap.get("page_categories") or [], "start_dates": [], "links": {},
        "whatsapp_from_ads": set(), "ad_ids": [], "keywords": set(),
    })
    if ad.get("start_date"):
        p["start_dates"].append(int(ad["start_date"]))
    if len(p["ad_ids"]) < 3:
        p["ad_ids"].append(str(ad.get("ad_archive_id")))
    links = [snap.get("link_url")] + [c.get("link_url") for c in (snap.get("cards") or []) if isinstance(c, dict)]
    for l in links:
        kind = classify_link(l)
        if kind == "whatsapp":
            n = wa_number(l)
            if n:
                p["whatsapp_from_ads"].add(n)
        elif kind:
            p["links"][l] = kind
    cap = (snap.get("caption") or "").strip().lower()
    if cap and "." in cap and " " not in cap:
        p.setdefault("captions", {})
        p["captions"][cap] = p["captions"].get(cap, 0) + 1
    return p


# ---------- stage A ----------
async def search_keyword(ctx, cc, kw, scrolls, pages):
    page = await ctx.new_page()
    bodies = []

    async def on_resp(r):
        if "graphql" in r.url and "AdLibrarySearchPaginationQuery" in (r.request.post_data or ""):
            try:
                bodies.append(await r.text())
            except Exception:
                pass
    page.on("response", on_resp)
    before = {pid for pid, p in pages.items() if kw in p["keywords"]}
    try:
        await page.goto(SEARCH_URL.format(cc=cc, q=quote(kw)), wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        html = await page.content()
        for conn in html_connections(html):
            for ad in iter_ads(conn):
                add_ad(pages, ad)["keywords"].add(kw)
        for _ in range(scrolls):
            await page.mouse.wheel(0, 25000)
            await page.wait_for_timeout(2500)
        for b in bodies:
            for j in json_chunks(b):
                for ad in iter_ads(j):
                    add_ad(pages, ad)["keywords"].add(kw)
        if "login" in page.url:
            log("WARN login wall on search", kw)
    except Exception as e:
        log("ERR search", kw, repr(e)[:200])
    finally:
        await page.close()
    mine = sum(1 for p in pages.values() if kw in p["keywords"]) - len(before)
    log(f"search '{kw}': {mine} pages")


# ---------- stage B ----------
async def page_detail(ctx, cc, p):
    page = await ctx.new_page()
    info_bodies = []

    async def on_resp(r):
        if "graphql" in r.url:
            try:
                t = await r.text()
            except Exception:
                return
            if "ig_username" in t or "ig_followers" in t or "page_alias" in t:
                info_bodies.append(t)
    page.on("response", on_resp)
    try:
        await page.goto(PAGE_URL.format(cc=cc, pid=p["page_id"]), wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3500)
        html = await page.content()
        m = re.search(r'"search_results_connection":\{"count":(\d+)', html)
        p["active_ads"] = int(m.group(1)) if m else None
        for conn in html_connections(html):
            for ad in iter_ads(conn):
                if str(ad.get("page_id")) == p["page_id"]:
                    add_ad({p["page_id"]: p}, ad)
        try:
            await page.get_by_text("About", exact=True).first.click(timeout=6000)
            for _ in range(16):
                await page.wait_for_timeout(500)
                if info_bodies:
                    break
            await page.wait_for_timeout(1000)
            body = await page.inner_text("body")
        except Exception:
            body = ""
        raw = "\n".join(info_bodies)
        g = lambda pat: (re.search(pat, raw) or [None, None])[1]
        p["ig_username"] = g(r'"ig_username":"([^"]+)"')
        f = g(r'"ig_followers":(\d+)')
        p["ig_followers"] = int(f) if f else None
        p["page_alias"] = g(r'"page_alias":"([^"]+)"')
        mc = re.search(r"Primary country location for people who manage this Page includes:[ \t]*([^\n]*)", body)
        val = mc.group(1).strip() if mc else ""
        p["manager_countries"] = val if re.search(r"\(\d+\)", val) else None
        p["detail_ok"] = p["active_ads"] is not None
    except Exception as e:
        p["detail_ok"] = False
        log("ERR page", p["page_id"], repr(e)[:200])
    finally:
        await page.close()


def finalize(p):
    sd = p["start_dates"]
    p["oldest_start"] = datetime.fromtimestamp(min(sd), timezone.utc).strftime("%Y-%m-%d") if sd else None
    p["days_running"] = int((NOW - min(sd)) // 86400) if sd else None
    sites = [l for l, k in p["links"].items() if k == "site"]
    caps = sorted((p.get("captions") or {}).items(), key=lambda x: -x[1])
    p["website_candidates"] = sites[:5]
    p["caption_domains"] = [c for c, _ in caps[:3]]
    p["link_kinds"] = sorted(set(p["links"].values()) | ({"whatsapp"} if p["whatsapp_from_ads"] else set()))
    p["whatsapp_from_ads"] = sorted(p["whatsapp_from_ads"])
    p["keywords"] = sorted(p["keywords"])
    p["ad_library_url"] = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&view_all_page_id={p['page_id']}&search_type=page"
    if p.get("ig_username"):
        p["ig_url"] = f"https://www.instagram.com/{p['ig_username']}/"
    p.pop("links", None); p.pop("captions", None); p.pop("start_dates", None)
    return p


def check_rules(p, mode, cc):
    r = RULES[mode]
    why = []
    ads, days = p.get("active_ads"), p.get("days_running")
    if ads is None:
        why.append("ad count unknown")
    else:
        if r["min_ads"] and ads < r["min_ads"]:
            why.append(f"ads {ads} < {r['min_ads']}")
        if r["max_ads"] and ads > r["max_ads"]:
            why.append(f"ads {ads} > {r['max_ads']}")
    if days is None or days < r["min_days"]:
        why.append(f"days {days} < {r['min_days']}")
    if mode == "clients":
        if not p.get("ig_username"):
            why.append("no instagram")
        else:
            f = p.get("ig_followers")
            if f is None or f < r["min_f"] or f > r["max_f"]:
                why.append(f"followers {f} outside {r['min_f']}-{r['max_f']}")
        name = COUNTRY_NAMES.get(cc, cc)
        mcs = p.get("manager_countries")
        if mcs and name.lower() not in mcs.lower():
            why.append(f"managed from {mcs}")
        elif not mcs:
            # manager country unknown: drop pages whose name/handle clearly points to another country
            text = f"{p.get('page_name') or ''} {p.get('ig_username') or ''}".lower()
            for code, hints in COUNTRY_HINTS.items():
                if code != cc and any(re.search(h, text) for h in hints):
                    why.append(f"name points to {code}")
                    break
    return why


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["refs", "clients"], required=True)
    ap.add_argument("--country", required=True)
    ap.add_argument("--keywords", required=True, help="'|' separated")
    ap.add_argument("--out", required=True)
    ap.add_argument("--want", type=int, default=0, help="stop stage B after this many pass (0 = no stop)")
    ap.add_argument("--scrolls", type=int, default=4)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-pages", type=int, default=250)
    ap.add_argument("--no-seen", action="store_true")
    ap.add_argument("--headful", action="store_true")
    a = ap.parse_args()
    cc = a.country.upper()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    kws = [k.strip() for k in a.keywords.split("|") if k.strip()]
    seen = set() if a.no_seen else seen_store.all_ids()

    pages = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not a.headful)
        ctx = await browser.new_context(locale="en-US", viewport={"width": 1366, "height": 900})
        sem = asyncio.Semaphore(a.workers)

        async def run_search(kw):
            async with sem:
                await search_keyword(ctx, cc, kw, a.scrolls, pages)
        await asyncio.gather(*(run_search(k) for k in kws))

        todo = [p for pid, p in pages.items() if pid not in seen]
        skipped_seen = len(pages) - len(todo)
        # refs: try pages with the oldest ads first; clients: any order
        todo.sort(key=lambda p: min(p["start_dates"] or [NOW]))
        todo = todo[: a.max_pages]
        log(f"stage B: {len(todo)} pages ({skipped_seen} skipped as seen)")

        passed, failed = [], []
        stop = asyncio.Event()

        async def run_detail(p):
            if stop.is_set():
                return
            async with sem:
                if stop.is_set():
                    return
                await page_detail(ctx, cc, p)
                finalize(p)
                why = check_rules(p, a.mode, cc)
                p["fail_reasons"] = why
                (failed if why else passed).append(p)
                if a.want and len(passed) >= a.want:
                    stop.set()
                done = len(passed) + len(failed)
                if done % 10 == 0:
                    log(f"  checked {done}/{len(todo)}, passed {len(passed)}")
        await asyncio.gather(*(run_detail(p) for p in todo))
        await browser.close()

    errors = sum(1 for p in failed if not p.get("detail_ok"))
    if a.mode == "refs":
        passed.sort(key=lambda p: -(p.get("days_running") or 0))
    result = {
        "mode": a.mode, "country": cc, "keywords": kws, "scanned_at": datetime.now().isoformat(timespec="seconds"),
        "stats": {"pages_found": len(pages), "skipped_seen": skipped_seen, "checked": len(passed) + len(failed),
                  "passed": len(passed), "detail_errors": errors},
        "passed": passed,
        "rejected_sample": [{"page_name": p["page_name"], "why": p["fail_reasons"]} for p in failed[:40]],
    }
    (out / "candidates.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=list), encoding="utf-8")
    log("done", result["stats"])
    print(json.dumps(result["stats"]))
    if errors and errors >= max(5, (len(passed) + len(failed)) // 2):
        log("FAIL: most page checks errored - Meta may have changed or blocked. Needs a fix.")
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
