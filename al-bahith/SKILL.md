---
name: al-bahith
description: الباحث / الكشاف (the Researcher / the Scout). Searches Meta Ad Library for active ads and returns ONE of two tables. المراجع (references) are strong websites of big advertisers (ad running 90+ days, 90+ active ads), USA by default, sorted by how long the ad has run, used for inspiration. عملائي (my clients) are small local advertisers (under 15 ads, ad running 7+ days, Instagram 1,000–70,000 followers) with no website or a very weak one, from the country the user names, with Instagram, followers, WhatsApp, email and where the lead was found. Clients can also come from Instagram itself: keyword search and hashtags in phone mode (iPhone emulation with the user's saved session), reading each profile's bio and its Contact button (email, phone, WhatsApp). A "no website" request returns only businesses with no working website. Self-contained (needs no other skill). Use when the user says "عملاء من الانستقرام", "دور بالانستقرام", "عملاء بدون موقع", "ما عندهم موقع", "no website", "الباحث", "الكشاف", "شغّل الكشاف", "scout", "أبي مراجع", "بدي مراجع", "أبي عملاء", "بدي عملاء", "دور لي عملاء", "دور لي مراجع", "researcher", "find references", or "find clients from ad library".
---

# الباحث (al-bahith)

Sources: **Meta Ad Library** (default) and **Instagram search/hashtags** in phone mode (clients only, step 3b). Talk to the user in Arabic (Gulf/Levantine, plain words).
Scripts: `~/.claude/skills/al-bahith/scripts/` (below, `scripts/…` means this folder; use the full path when you run them).
Data folder (`<data>`): run `python scripts/paths.py` to print it. The default is `~/al-bahith`; it can be changed with `config.json` in the skill folder (`{"data_dir": "..."}`) or the env `AL_BAHITH_DATA`.
Run every script with the system Python (`python`, or `python3` on Mac). Needs `pip install "scrapling[fetchers]" openpyxl`, then `scrapling install`, once. If an import fails, install those first and tell the user.

## 0. Which mode?
- "مراجع" means **refs mode**. It makes the المراجع table only.
- "عملاء" means **clients mode**. It makes the عملائي table only.
- If it is not clear, ask: "مراجع ولا عملاء؟". Never make both tables in one run.

| | refs | clients |
|---|---|---|
| Country | `US` unless the user names one (KW, SA, AE, QA, BH, OM, GB…) | **Must** be named by the user. If not, ask |
| Target | 10–20 rows (default 20) | 50 rows |
| Ad rule (script) | active ads > 90 AND an ad running ≥ 90 days | active ads < 15 AND an ad running ≥ 7 days |
| Other (script) | — | Instagram linked to the page, 1,000–70,000 followers, page managed from the country (or unknown) |
| Site rule | score 7–10 only | no site or score 0–4 goes in the table; 5–6 goes to the "وسط" sheet; 7–10 goes to the "شيك عليها" sheet |

Never loosen a rule on your own. If too few results pass (for example a Gulf country in refs mode), say how many were found and ask before changing anything.

## 1. Keywords (always confirmed first)
- The user named a field: build 8–15 Arabic and English keywords for it (see the "Field-specific runs" section of `references/keywords-all-fields.md`).
- No field named: pick 12–20 from `references/keywords-all-fields.md` (Gulf list for clients, USA list for US refs), preferring keywords not used in recent runs.
- Show them as a numbered list and **wait for the user's OK**. Then start.

## 2. Run folder
`$RUN = <data>/runs/<YYYY-MM-DD>_<refs|clients>_<CC>_<field>` (add `_2`, `_3`… if it already exists). This is a working folder only (JSON and screenshots). The tables always go to the one Excel file.

## 3. Scan Ad Library (background, about 3–10 min)
```
python scripts/adlib_scan.py --mode clients --country KW --keywords "kw1|kw2|..." --out "$RUN" --want 70 --scrolls 4 --workers 5 --max-pages 400
python scripts/adlib_scan.py --mode refs    --country US --keywords "kw1|kw2|..." --out "$RUN" --want 35 --scrolls 8 --workers 5 --max-pages 400
```
- `--want` oversamples, because some pages drop out at the site step. Clients: 70 for 50 rows. Refs: 35 for 20 rows.
- It skips pages already shown in earlier runs (`seen.json`).
- Output: `$RUN/candidates.json` → `passed` (with page name, `ig_username`, `ig_followers`, `active_ads`, `days_running`, `oldest_start`, ad links, WhatsApp numbers from ads, `manager_countries`) plus `rejected_sample` (why pages failed).
- Too few passed? Suggest more or different keywords to the user, and run again with them into the same `$RUN` folder under a new `--out` subfolder, then merge. Or tell the user the count.

## No-website runs (user rule, 2026-11-15)
When the user asks for clients **with no website** ("بدون موقع", "ما عندهم موقع", "no website"):
- Check the bio links and the Contact button data. A business with a working website is **skipped completely**: not scored, and not put in «وسط» or «شيك عليها».
- Only these count as "no website": no link, or only WhatsApp/Instagram/link-hub pages (Linktree, reach.link…), or a site that does not load.
- Hidden websites (fixed 2026-11-16): `site_check.py` / `--no-site` open every link hub (Linktree, reach.link, iwtsp…) and read the sites listed inside, read domains written in the bio text, and the domain of a business email (not gmail/hotmail/icloud…). Every candidate is tried until one loads. A lead whose site hides behind one of these is NOT a no-website lead.
- The «عملائي» and «وسط» sheets always have a «الموقع التجريبي» column (added to old files too); bani-al-demo fills it.
- Use `--no-site` on `ig_search.py` (it checks each lead's link live and rejects working sites) and on `write_xlsx.py`. The target number counts only no-website businesses. No scoring step is needed, but the field check (step 6b) still is.

## 3b. Clients only: Instagram as a second source (`ig_search.py`)
Use it when the user asks for Instagram ("من الانستقرام", "دوّر بالانستقرام", "hashtags"), or when Ad Library is blocked or gives too few leads. It uses the saved Instagram session in **phone mode** (iPhone screen + User-Agent), where keyword search and hashtag pages show posts the way the app does.
```
python scripts/ig_search.py --country KW --keywords "perfume kuwait|عطور الكويت" --hashtags "عطور_الكويت|perfumekuwait" --niche "عطور|عطر|بخور|عود|perfume|fragrance|oud|..." --out "$RUN" --cap 400 --want 50 [--no-site]
```
- Run it in the background with output to a log file (`> "$RUN/run.log" 2>&1`, and `python -u`) and watch the log. In PowerShell, don't use `2>&1` straight on python: it shows progress lines as fake errors.
- `--want N`: stop once N leads pass. With `--no-site` only no-website leads count, so "50 clients with no website" = `--want 50 --no-site`. Without it, about half the leads end up in عملائي after scoring, so ask for about twice the target.
- About 1 in 5–10 profiles read becomes a no-website lead in a busy niche like perfume, so 50 leads need about 300–400 profile reads (1–1.5 h at the safe pace). Tell the user the expected time before starting.
- Accounts rejected in earlier Instagram runs are not read again. Accounts that only failed to load (internet cut) are not counted as rejected. After 5 failed loads in a row the run stops with `NETWORK`; rerun the same command when the internet is back.
- Keywords: build them like step 1 (niche + country, in Arabic and English) and also 1–3 hashtags. Also build `--niche`, the field's own words in Arabic and English, including dialect, singular and plural, and product names. For perfume: `"عطور|عطر|عطورات|بخور|عود|دهن|مسك|طيب|معطر|perfume|parfum|fragrance|scent|oud|bakhoor|bukhoor|musk|attar"`. Show the keywords, hashtags and niche words to the user and wait for an OK. Always pass `--niche`: without it, any business tagged in a post can pass.
- Phase 1 collects every account that posted in the results, plus every `@shop` tagged in their captions. A shop that pays influencers already spends on marketing, so tagged shops are read first.
- Phase 2 reads each new profile, paced 5–10 s, up to `--cap`. For accounts in the follower range it also reads the **Contact button** data: the email, phone and WhatsApp the business set in the app (often not in the bio). It reads it the way the iPhone app does, with the same saved session (`contact_card` in `ig_profile.py`). After 3 refusals in a row it skips that for the rest of the run. `ig_profile.py` does the same for Ad Library leads. It keeps only: 1,000–70,000 followers, a business (not an influencer or creator, unless the bio says it sells), not private, and a sign it is in the country (a local phone number, or the country or `kw`/`q8` in the name, handle or bio). A foreign phone number drops it.
- It writes `candidates.json` and `ig.json` like steps 3–4, so **skip step 4** and continue with step 5. Do step 6b (field check) before step 7. The «وين لقيته» column gets the post link where the account was found, and «كلمة البحث» says which search or tag found it.
- No ad data for these, so «عدد الإعلانات» and «مدة الإعلان» stay empty.
- Exit 4 (`LOGIN_WALL` / `RATE_LIMIT` / `NETWORK`): stop and tell the user. Rerunning the same command continues where it stopped (`ig_found.json` keeps the search results; delete it to search again).
- Tested 2026-11-15 on perfume, Kuwait: 7 keywords + 5 hashtags found 536 accounts in 5 min. 180 profiles read gave 28 no-website shops, 25 with WhatsApp and 12 with email (most emails came from the Contact button).

## 4. Clients only: Instagram contacts (background, start right after step 3)
Followers already come from Ad Library. Instagram is read only for the bio, the website link, WhatsApp and email. The script opens each profile page with the saved session and reads the profile's embedded data. It picks up `wa.me` links and local mobile numbers written in the bio, for example "50 70 46 58" in Kuwait. About 13 s per profile.
- `PARSE_FAIL`: Instagram changed its page data. Follow "When a script fails" below (fix `profile_object` in `ig_profile.py`).
- `write_xlsx.py` drops a client when all of its phone numbers belong to another country, for example a +971 number in a Kuwait run.
```
python scripts/ig_profile.py --in "$RUN/candidates.json" --out "$RUN/ig.json" --cap 80
```
- `NO_SESSION` or `LOGIN_WALL`: ask the user to run the login. Say: «لازم تسجل دخول انستقرام مرة وحدة بنفسك». Then run `python scripts/ig_profile.py --login` (it opens a window; **the user types their own password, never Claude**). Then rerun. The output file resumes where it stopped.
- `RATE_LIMIT`: stop Instagram, tell the user, and go on with what was read. Contacts for the rest show as "غير متوفر".
- While it runs (about 5–10 s per profile), do step 5 at the same time.

## 5. Websites (parallel)
```
python scripts/site_check.py --in "$RUN/candidates.json" --out "$RUN/sites.json"
python scripts/shots.py --in "$RUN/sites.json" --dir "$RUN/shots"
```
- In clients mode, run `site_check.py` **after** `ig.json` exists if possible, because the Instagram bio link can be the only website. If Instagram is still running, run it now and then rerun it at the end (it is cheap) before step 7.
- Speed (criterion c1) is measured by `shots.py` while it takes the screenshots: mobile `load_seconds`, where under 3 s passes. No Lighthouse by default. `site_check.py --psi` adds Lighthouse/PageSpeed only if the user asks for it.

## 6. Score the sites by eye
Only for pages where `sites.json` has `kind == "site"` and `shots/shots.json` has screenshots. Follow `references/site-score.md` exactly. Look at `<id>_m1.jpg`, `<id>_m2.jpg` and `<id>_d1.jpg`. Speed and tracking are scored by the scripts, not by eye.
- Up to 10 sites: score them yourself and write `$RUN/scores.json`.
- More than 10: split them into batches of about 10 and send each batch to a subagent (general-purpose) with: the path of `references/site-score.md`, the list of `page_id` with their image paths and `pagespeed_mobile`, and the output file `$RUN/scores_part<N>.json`. Run the batches in parallel.
- Clients mode: no need to score pages with no real site.

## 6b. Field check by eye (always, before the Excel step; user rule 2026-11-16)
Never give the user a lead outside their field. A perfume search can bring in a bakery, a restaurant, a delivery app or a general store (they show up because an influencer tagged them).
```
python scripts/review.py list "$RUN"
python scripts/review.py drop "$RUN" handle1,handle2 --why "bakery, not perfume"
```
- Read each line (name, category, bio). Keep only businesses that **sell in the field** the user asked for. Drop:
  - other kinds of business;
  - suppliers to the field (packaging, printing, factories) unless the user asked for them;
  - an empty or vague bio with nothing that ties it to the field.
- Tell the user in one line how many were dropped and why, then go on to step 7.

## 7. Build the tables
```
python scripts/write_xlsx.py --run "$RUN" --field "<field or all>" --want <20|50>
python scripts/seen.py add <refs|clients> "$RUN/final.json"
```
**There is only ONE Excel file, for every run: `<data>/الباحث.xlsx`.** It has 4 sheets: «المراجع», «عملائي», «شيك عليها» and «وسط». Each run **adds** its rows to the right sheets:
- Old rows stay as they are, including any notes or columns the user added.
- A page already in a sheet is not added again.
- «المراجع» is re-sorted by days running, longest first.
- Every row gets the country, the field and the search date.

Never create a separate xlsx per run. If the file is open in Excel, the script saves to `الباحث_جديد.xlsx` and warns. Ask the user to close Excel, then run `python scripts/write_xlsx.py --from-final "$RUN/final.json"` to add the rows to the main file, and delete the `_جديد` copy.

## 8. Report in the chat (Arabic, short)
- The file path (always `<data>/الباحث.xlsx`) and how many new rows went into each sheet (`added` in the script output).
- Counts: rows, «شيك عليها», «وسط», pages scanned.
- The first 10 rows as a small table. Refs columns: name, site, days. Clients columns: name, Instagram, followers, site yes/no, WhatsApp.
- Clients mode: list «شيك عليها» (name, site, why strong) and say: «هذول مواقعهم قوية، شيك عليهم، وإذا عجبوك أضيفهم للمراجع». If the user approves some, add them as rows to the «المراجع» sheet of `الباحث.xlsx`. Edit it with openpyxl, keep the column order, and re-sort by days. Remove them from «شيك عليها».
- Anything that did not work (Instagram stopped, speed unknown, few results).

## When a script fails
1. Stop and tell the user in one line what broke (quote the shortest error line).
2. Try a **quick fix** to the script first. Likely causes: Meta renamed a field (inspect a fresh response, as in `adlib_scan.py` `iter_ads` / `page_detail`), or a selector or text changed (for example the "About" tab).
3. Only if there is no quick fix, tell the user, then fall back to Claude in Chrome (Ad Library in the browser: search URL, then the page's "About" for Instagram and followers). This is slower; say so.
- `adlib_scan.py` exits with code 2 when most page checks fail. Treat that as "Meta changed or blocked".

## Rules
- Never type the user's passwords and never sign in for them.
- Keep Instagram reading paced (the default 5–10 s, cap 80 per run).
- Never put the same page in two runs (`seen.json`). To show a page again, the user must ask.
- The user's country for clients is exact. Pages managed from another country are dropped. Pages with an unknown manager country are kept and marked «غير معروف».
