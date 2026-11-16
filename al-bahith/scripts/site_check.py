"""Website technical check for al-bahith.

  python site_check.py --in candidates.json --out sites.json [--workers 12] [--psi]
  python site_check.py --url https://example.com           (single URL, prints JSON)

Per page: picks the main website (ad caption domain first, then ad link, then Instagram links if
ig.json is next to candidates.json), then reports: loads, final_url, kind (site / whatsapp / social /
linkhub / none / broken), https, platform (shopify/salla/zid/wix/wordpress/...), meta_pixel, google_analytics,
whatsapp numbers + emails found on the page, and mobile PageSpeed performance (0-100, or null if unavailable).
Set env PSI_KEY for a Google API key if the keyless PageSpeed quota runs out.
"""
import argparse, json, os, re, sys, time, pathlib
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, quote
from curl_cffi import requests

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from adlib_scan import classify_link, WA  # noqa: E402

NOT_SITES = ("amazon.", "walmart.", "target.com", "ebay.", "noon.com", "talabat", "deliveroo", "apple.com/app",
             "apps.apple.com", "play.google.com", "pscrpt.io", "mikmak", "bit.ly", "tinyurl", "linktr.ee",
             "onelink.me", "app.link", "page.link", "shop.app", "tiktok.com", "snapchat.com", "youtube.com", "x.com",
             "twitter.com", "google.com", "goo.gl", "maps.app")
EMAIL_RE = re.compile(r"mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
WA_RE = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send/?\?phone=|whatsapp\.com/send/?\?phone=)\+?(\d{7,15})", re.I)
PLATFORMS = [("shopify", r"cdn\.shopify\.com|Shopify\.theme"), ("salla", r"salla\.(sa|network)|cdn\.salla"),
             ("zid", r"zid\.store|zidcdn|cdn\.zid"), ("wix", r"wixstatic\.com|_wixCIDX"),
             ("squarespace", r"squarespace\.com"), ("wordpress", r"wp-content|wp-includes"),
             ("webflow", r"webflow\.(com|io)"), ("woocommerce", r"woocommerce"), ("framer", r"framerusercontent")]


def home(url):
    u = urlparse(url if "://" in url else "https://" + url)
    return f"{u.scheme or 'https'}://{u.netloc}/"


FREE_MAIL = ("gmail.", "hotmail.", "outlook.", "yahoo.", "icloud.", "live.", "msn.", "aol.", "proton", "mail.ru",
             "yandex.", "me.com", "windowslive.")
# a domain written in plain text (bio, link-hub page): www.shop.com / shop.com.kw / https://shop.store
DOMAIN_RE = re.compile(r"(?<![@\w.-])(?:https?://)?(?:www\.)?((?:[a-z0-9-]+\.)+(?:com|net|org|co|shop|store|online|me|"
                       r"kw|sa|ae|qa|bh|om|com\.kw|com\.sa|net\.kw|uk|co\.uk|io|app|site|boutique|perfume|beauty))"
                       r"(?![\w-])", re.I)
HREF_RE = re.compile(r"""href=["'](https?://[^"'\s>]+)""", re.I)
# hosts that show up inside link-hub pages but are never the client's own website
HUB_NOISE = ("linktr", "reach", "iwtsp", "beacons", "bio.link", "cdn", "fonts", "w3.org", "schema.org", "cloudflare",
             "sentry", "gstatic", "googleapis", "jsdelivr", "unpkg", "datagrail", "spotify", "linkedin", "clarity.ms",
             "threads", "fontawesome", "doubleclick", "facebook.net", "vercel", "amazonaws", "imgix", "t.me",
             "telegram", "mysyara", "hotjar", "segment", "intercom", "stripe", "paypal", "boutiqaat", "enabill")
_HUB_CACHE = {}


def hub_links(url):
    """Outbound website domains listed on a link-hub page (Linktree, reach.link, ...). Network call, cached."""
    if url in _HUB_CACHE:
        return _HUB_CACHE[url]
    out = []
    try:
        r = requests.get(url, impersonate="chrome", timeout=20, allow_redirects=True)
        html = r.text or ""
        for l in HREF_RE.findall(html) + re.findall(r'"url"\s*:\s*"(https?:[^"]+)"', html):
            l = l.replace("\\/", "/")
            host = urlparse(l).netloc.lower().removeprefix("www.")
            if host and classify_link(l) == "site" and not any(n in host for n in HUB_NOISE + NOT_SITES):
                out.append(host)
    except Exception:
        pass
    _HUB_CACHE[url] = list(dict.fromkeys(out))
    return _HUB_CACHE[url]


def site_candidates(p, ig=None, follow_hubs=True):
    """Every place a lead's own website can hide, best first: ad caption/links, Instagram bio links, sites listed
    inside link-hub pages (Linktree...), domains written in the bio text, and the domain of a business email."""
    cands, hubs = [], []
    for c in p.get("caption_domains") or []:
        cands.append(c)
    links = list(p.get("website_candidates") or []) + list((ig or {}).get("links") or [])
    for l in links:
        k = classify_link(l)
        if k == "site":
            cands.append(urlparse(l).netloc)
        elif k == "linkhub":
            hubs.append(l)
    if ig:
        cands += [m for m in DOMAIN_RE.findall(ig.get("bio") or "")]
    if follow_hubs:
        for h in dict.fromkeys(hubs):
            cands += hub_links(h)
    emails = list((ig or {}).get("emails") or []) + [((ig or {}).get("contact_button") or {}).get("email") or ""]
    for e in emails:
        if "@" in e:
            d = e.split("@", 1)[1].lower()
            if not any(f in d for f in FREE_MAIL):
                cands.append(d)
    seen, out = set(), []
    for c in cands:
        c = (c or "").lower().strip().removeprefix("www.").rstrip("/.")
        if c and c not in seen and not any(n in c for n in NOT_SITES + HUB_NOISE) \
                and classify_link("https://" + c) == "site":
            seen.add(c)
            out.append(home(c))
    return out, hubs


def pick_site(p, ig=None, follow_hubs=True):
    cands, hubs = site_candidates(p, ig, follow_hubs)
    if cands:
        return {"kind": "site", "url": cands[0], "candidates": cands}
    if hubs:
        return {"kind": "linkhub", "url": hubs[0]}
    if p.get("whatsapp_from_ads"):
        return {"kind": "whatsapp", "url": None}
    if "social" in (p.get("link_kinds") or []):
        return {"kind": "social", "url": None}
    return {"kind": "none", "url": None}


_CHROME = None


def chrome_path():
    global _CHROME
    if _CHROME is None:
        from patchright.sync_api import sync_playwright
        with sync_playwright() as p:
            _CHROME = p.chromium.executable_path
    return _CHROME


import threading
_LH_SEM = threading.Semaphore(3)  # max 3 Lighthouse runs at once (CPU heavy)


def lighthouse(url):
    with _LH_SEM:
        return _lighthouse(url)


def _lighthouse(url):
    """Local Lighthouse mobile performance (same engine as PageSpeed Insights)."""
    import subprocess, tempfile
    out = pathlib.Path(tempfile.mkdtemp()) / "lh.json"
    env = dict(os.environ, CHROME_PATH=chrome_path())
    try:
        subprocess.run(["npx", "--yes", "lighthouse", url, "--only-categories=performance", "--output=json",
                        f"--output-path={out}", "--chrome-flags=--headless=new", "--quiet", "--max-wait-for-load=45000"],
                       env=env, timeout=150, capture_output=True, shell=(os.name == "nt"))
        s = json.loads(out.read_text(encoding="utf-8"))["categories"]["performance"]["score"]
        return (round(s * 100), None) if s is not None else (None, "lighthouse no score")
    except Exception as e:
        return None, "lighthouse failed: " + repr(e)[:80]


def psi(url):
    key = os.environ.get("PSI_KEY")
    if not key:
        return lighthouse(url)
    api = ("https://www.googleapis.com/pagespeedonline/v5/runPagespeed?category=performance&strategy=mobile&url="
           + quote(url, safe="") + (f"&key={key}" if key else ""))
    for attempt in range(2):
        try:
            r = requests.get(api, timeout=90)
            if r.status_code == 200:
                s = r.json()["lighthouseResult"]["categories"]["performance"]["score"]
                return round(s * 100) if s is not None else None, None
            if r.status_code == 429:
                time.sleep(5)
                continue
            break
        except Exception:
            break
    return lighthouse(url)


def check(url, do_psi=True):
    res = {"url": url, "loads": False, "final_url": None, "kind": "broken", "https": False, "platform": None,
           "meta_pixel": False, "google_analytics": False, "whatsapp": [], "emails": [], "pagespeed_mobile": None,
           "error": None}
    try:
        r = requests.get(url, impersonate="chrome", timeout=25, allow_redirects=True)
        res["final_url"] = str(r.url)
        k = classify_link(res["final_url"])
        html = r.text or ""
        if r.status_code in (401, 403, 429, 503) and k == "site":
            # bot wall for scripts; a real browser (shots.py) decides if it loads
            res.update(kind="site", loads=None, https=res["final_url"].startswith("https://"),
                       error=f"protected (http {r.status_code}); checked in browser")
            if do_psi:
                res["pagespeed_mobile"], _ = psi(res["final_url"])
            return res
        if r.status_code >= 400 or len(html) < 500:
            res["error"] = f"http {r.status_code}, {len(html)} bytes"
            return res
        if k != "site":
            res["kind"] = k
            return res
        res.update(loads=True, kind="site", https=res["final_url"].startswith("https://"))
        for name, pat in PLATFORMS:
            if re.search(pat, html, re.I):
                res["platform"] = name
                break
        res["meta_pixel"] = bool(re.search(r"fbevents\.js|fbq\(", html))
        res["google_analytics"] = bool(re.search(r"googletagmanager\.com|gtag\(|google-analytics\.com", html))
        res["whatsapp"] = sorted(set(WA_RE.findall(html)))[:3]
        res["emails"] = sorted({e for e in EMAIL_RE.findall(html) if not e.endswith((".png", ".jpg"))})[:3]
        if do_psi:
            res["pagespeed_mobile"], res["error"] = psi(res["final_url"])
    except Exception as e:
        res["error"] = repr(e)[:160]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--out")
    ap.add_argument("--url")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--psi", action="store_true", help="also run PageSpeed/Lighthouse (slow; speed is normally measured by shots.py)")
    a = ap.parse_args()
    if a.url:
        print(json.dumps(check(a.url, a.psi), ensure_ascii=False, indent=1))
        return
    inp = pathlib.Path(a.inp)
    data = json.loads(inp.read_text(encoding="utf-8"))
    igf = inp.parent / "ig.json"
    igd = json.loads(igf.read_text(encoding="utf-8")) if igf.exists() else {}
    jobs, out = [], {}
    for p in data["passed"]:
        pick = pick_site(p, igd.get(p.get("ig_username") or ""))
        out[p["page_id"]] = {"page_id": p["page_id"], "page_name": p["page_name"], **pick}
        if pick["kind"] == "site":
            jobs.append(p["page_id"])
    def first_working(pid):
        # try every candidate (bio link, link-hub sites, bio text, email domain) until one really loads
        cands = out[pid].get("candidates") or [out[pid]["url"]]
        first = None
        for u in cands:
            r = check(u, a.psi)
            first = first or r
            if r["kind"] == "site" and r["loads"] is not False:
                out[pid]["url"] = u
                return r
        return first

    with ThreadPoolExecutor(a.workers) as ex:
        for pid, r in zip(jobs, ex.map(first_working, jobs)):
            out[pid]["check"] = r
            out[pid]["kind"] = r["kind"]
    pathlib.Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds = {}
    for v in out.values():
        kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    print(json.dumps({"pages": len(out), "kinds": kinds}))


if __name__ == "__main__":
    main()
