"""Screenshots for website scoring (al-bahith).

  python shots.py --in sites.json --dir run_dir/shots [--workers 4]

For every entry with kind == "site": mobile first screen (390x844), mobile scroll (full page, max 3 screens)
and desktop first screen (1440x900). Saves JPGs <page_id>_m1.jpg, _m2.jpg, _d1.jpg and writes shots.json.
Also measures mobile load_seconds: Largest Contentful Paint on a normal connection (criterion c1: < 3 s passes).
"""
import argparse, asyncio, json, pathlib, re, sys
from patchright.async_api import async_playwright

MOBILE = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True, "device_scale_factor": 1,
          "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"}
DESKTOP = {"viewport": {"width": 1440, "height": 900}}


# Largest Contentful Paint = when the main content of the first screen appears (ms since navigation start)
LCP_JS = """new PerformanceObserver(l => { const e = l.getEntries(); if (e.length) window.__lcp = e[e.length-1].startTime; })
  .observe({type: 'largest-contentful-paint', buffered: true});"""

CLOSE_SEL = ('[aria-label*="close" i], [aria-label*="dismiss" i], [aria-label*="إغلاق"], button.close, .modal-close, '
             '[class*="close-button" i], [class*="popup-close" i], [data-testid*="close" i], '
             'button:has-text("No thanks"), button:has-text("Accept"), button:has-text("موافق")')


async def close_popups(page):
    """Best effort: dismiss newsletter/cookie popups so the screenshot shows the real page."""
    for _ in range(2):
        try:
            await page.keyboard.press("Escape")
            els = await page.query_selector_all(CLOSE_SEL)
            for el in els[:4]:
                if await el.is_visible():
                    await el.click(timeout=1500)
                    await page.wait_for_timeout(400)
        except Exception:
            pass
    await page.wait_for_timeout(500)


async def shoot(browser, url, base, sem):
    files = {}
    async with sem:
        for tag, opts in (("m", MOBILE), ("d", DESKTOP)):
            ctx = await browser.new_context(**opts)
            page = await ctx.new_page()
            if tag == "m":
                await page.add_init_script(LCP_JS)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(3500)
                if tag == "m":
                    try:
                        await page.wait_for_load_state("load", timeout=12000)
                    except Exception:
                        pass
                    ms = await page.evaluate("""() => {
                        if (window.__lcp) return window.__lcp;
                        const n = performance.getEntriesByType('navigation')[0];
                        return n && n.loadEventEnd > 0 ? n.loadEventEnd : null; }""")
                    files["load_seconds"] = round(ms / 1000, 1) if ms else None
                await close_popups(page)
                f1 = f"{base}_{tag}1.jpg"
                await page.screenshot(path=f1, type="jpeg", quality=60)
                files[f"{tag}1"] = f1
                if tag == "m":
                    html = await page.content()
                    files["browser_loads"] = len(html) > 1500 and not re.search(
                        r"Access denied|Just a moment|Attention Required|captcha", html[:20000], re.I)
                    files["meta_pixel"] = bool(re.search(r"fbevents\.js|fbq\(", html))
                    files["google_analytics"] = bool(re.search(r"googletagmanager\.com|gtag\(|google-analytics\.com", html))
                    h = min(await page.evaluate("document.body.scrollHeight"), 844 * 3)
                    f2 = f"{base}_m2.jpg"
                    await page.screenshot(path=f2, type="jpeg", quality=55, full_page=True,
                                          clip={"x": 0, "y": 0, "width": 390, "height": max(h, 844)})
                    files["m2"] = f2
            except Exception as e:
                files[f"{tag}_error"] = repr(e)[:150]
            finally:
                await ctx.close()
    return files


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    d = pathlib.Path(a.dir); d.mkdir(parents=True, exist_ok=True)
    sites = json.loads(pathlib.Path(a.inp).read_text(encoding="utf-8"))
    todo = [(pid, v["check"]["final_url"] or v["url"]) for pid, v in sites.items()
            if v["kind"] == "site" and v.get("check", {}).get("loads") is not False]
    sem = asyncio.Semaphore(a.workers)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        res = await asyncio.gather(*(shoot(browser, u, str(d / re.sub(r'[\\/:*?"<>|]', "_", pid)), sem) for pid, u in todo))
        await browser.close()
    out = {pid: r for (pid, _), r in zip(todo, res)}
    (d / "shots.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({"shot": len(out), "errors": sum(1 for r in out.values() if any(k.endswith("error") for k in r))}))


if __name__ == "__main__":
    asyncio.run(main())
