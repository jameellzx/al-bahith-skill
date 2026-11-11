"""Instagram contact reader for al-bahith (الباحث). Uses the user's own saved session.

  python ig_profile.py --login                 -> opens a window; the USER signs in themselves; session saved
  python ig_profile.py --in candidates.json --out ig.json [--cap 80] [--min-wait 5] [--max-wait 10]

For every passed page with ig_username it reads: biography, external_url, bio links,
business email / phone, category, followers. Then pulls WhatsApp numbers and emails from the bio.
Paced, capped, resumable (rerun with the same --out to continue). Stops cleanly on a login wall or rate limit.
"""
import argparse, asyncio, json, random, re, sys, time, pathlib
from patchright.async_api import async_playwright

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from paths import IG_STATE as STATE  # noqa: E402
PROFILE = "https://www.instagram.com/{u}/"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
WA_RE = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp\.com/send\?phone=)\+?(\d{7,15})", re.I)
PHONE_RE = re.compile(r"(?:\+|00)?(?:965|966|971|974|973|968)[\s-]?\d{3,4}[\s-]?\d{3,4}")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


async def login():
    STATE.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(str(STATE), headless=False, no_viewport=True)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.instagram.com/accounts/login/")
        log("Sign in to Instagram in the window. Waiting up to 10 minutes...")
        for _ in range(600):
            cookies = await ctx.cookies("https://www.instagram.com")
            if any(c["name"] == "sessionid" and c["value"] for c in cookies):
                log("Signed in. Session saved to", STATE)
                await page.wait_for_timeout(3000)
                await ctx.close()
                print("LOGIN_OK")
                return
            await page.wait_for_timeout(1000)
        await ctx.close()
        print("LOGIN_TIMEOUT")
        sys.exit(3)


def profile_object(html, handle):
    """Find the profile's own user object inside the page's embedded JSON."""
    dec = json.JSONDecoder()
    for m in re.finditer(r'"user":\{', html):
        try:
            obj, _ = dec.raw_decode(html, m.start() + 7)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("username", "").lower() == handle.lower() and "biography" in obj:
            return obj
    return None


# local mobile numbers written in a bio without country code (digits may be spaced): code, regex on digits only
LOCAL_MOBILE = {"KW": ("965", r"[569]\d{7}"), "BH": ("973", r"3\d{7}"), "QA": ("974", r"[3567]\d{7}"),
                "OM": ("968", r"[79]\d{7}"), "AE": ("971", r"05\d{8}"), "SA": ("966", r"05\d{8}")}


def extract(user, cc=None):
    bio = user.get("biography") or ""
    links = [l.get("url") for l in (user.get("bio_links") or []) if l.get("url")]
    if user.get("external_url"):
        links.insert(0, user["external_url"])
    links = list(dict.fromkeys(links))
    text = bio + " " + " ".join(links)
    wa = set(WA_RE.findall(text))
    for k in ("public_phone_number", "contact_phone_number", "business_phone_number"):
        if user.get(k):
            ph = re.sub(r"\D", "", str(user.get("public_phone_country_code") or "") + str(user[k]))
            if ph:
                wa.add(ph)
    phones = {re.sub(r"\D", "", p) for p in PHONE_RE.findall(bio)}
    if cc in LOCAL_MOBILE:
        code, pat = LOCAL_MOBILE[cc]
        for chunk in re.findall(r"(?<!\d)(?:\d[\s-]?){8,10}(?!\d)", bio):
            d = re.sub(r"\D", "", chunk)
            if re.fullmatch(pat, d):
                phones.add(code + d.lstrip("0"))
    known = {p[-8:] for p in wa}
    phones = {p for p in phones if p[-8:] not in known}
    emails = set(EMAIL_RE.findall(bio))
    for k in ("public_email", "business_email"):
        if user.get(k):
            emails.add(user[k])
    return {
        "full_name": user.get("full_name"), "bio": bio, "links": links,
        "category": user.get("category") or user.get("category_name"), "is_business": user.get("is_business"),
        "followers": user.get("follower_count"),
        "whatsapp": sorted(wa | phones), "emails": sorted(emails),
    }


async def read_all(inp, outp, cap, wmin, wmax):
    data = json.loads(pathlib.Path(inp).read_text(encoding="utf-8"))
    cc = data.get("country")
    handles = [p["ig_username"] for p in data.get("passed", []) if p.get("ig_username")]
    out = json.loads(pathlib.Path(outp).read_text(encoding="utf-8")) if pathlib.Path(outp).exists() else {}
    todo = [h for h in handles if h not in out][:cap]
    log(f"{len(todo)} profiles to read ({len(out)} already done)")
    if not STATE.exists():
        print("NO_SESSION: run ig_profile.py --login first"); sys.exit(3)
    status = "OK"
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(str(STATE), headless=True)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        if "login" in page.url:
            print("LOGIN_WALL: session expired, run --login again"); await ctx.close(); sys.exit(3)
        misses = 0
        for i, h in enumerate(todo, 1):
            try:
                resp = await page.goto(PROFILE.format(u=h), wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(2500)
                st = resp.status if resp else 0
                html = await page.content()
            except Exception as e:
                out[h] = {"error": "load " + repr(e)[:80]}
                continue
            if "accounts/login" in page.url or "/challenge" in page.url:
                status = "LOGIN_WALL"; break
            if st == 429 or "Please wait a few minutes" in html:
                status = "RATE_LIMIT"; break
            user = profile_object(html, h)
            if user:
                out[h] = extract(user, cc)
                misses = 0
            else:
                out[h] = {"error": "not found" if st == 404 or "Page Not Found" in html[:3000] else "parse"}
                misses += out[h]["error"] == "parse"
                if misses >= 5:
                    status = "PARSE_FAIL"; break  # Instagram changed its page data
            pathlib.Path(outp).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
            if i % 10 == 0:
                log(f"  {i}/{len(todo)}")
            await page.wait_for_timeout(int(random.uniform(wmin, wmax) * 1000))
        await ctx.close()
    pathlib.Path(outp).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    left = len([h for h in handles if h not in out])
    print(json.dumps({"status": status, "read": len(out), "left": left}))
    if status != "OK":
        sys.exit(4)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--out")
    ap.add_argument("--cap", type=int, default=80)
    ap.add_argument("--min-wait", type=float, default=5)
    ap.add_argument("--max-wait", type=float, default=10)
    a = ap.parse_args()
    asyncio.run(login() if a.login else read_all(a.inp, a.out, a.cap, a.min_wait, a.max_wait))
