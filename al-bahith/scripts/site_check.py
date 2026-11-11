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


def pick_site(p, ig=None):
    cands = []
    for c in p.get("caption_domains") or []:
        cands.append(c)
    for l in p.get("website_candidates") or []:
        cands.append(urlparse(l).netloc)
    if ig:
        for l in ig.get("links") or []:
            k = classify_link(l)
            if k == "site":
                cands.append(urlparse(l).netloc)
            elif k == "linkhub" and not cands:
                return {"kind": "linkhub", "url": l}
    for c in cands:
        c = c.lower().removeprefix("www.")
        if c and not any(n in c for n in NOT_SITES) and classify_link("https://" + c) == "site":
            return {"kind": "site", "url": home(c)}
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
    with ThreadPoolExecutor(a.workers) as ex:
        for pid, r in zip(jobs, ex.map(lambda pid: check(out[pid]["url"], a.psi), jobs)):
            out[pid]["check"] = r
            out[pid]["kind"] = r["kind"]
    pathlib.Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds = {}
    for v in out.values():
        kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    print(json.dumps({"pages": len(out), "kinds": kinds}))


if __name__ == "__main__":
    main()
