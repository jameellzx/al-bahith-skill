---
name: al-bahith
description: الباحث / الكشاف (the Researcher / the Scout). Searches Meta Ad Library for active ads and returns ONE of two tables. المراجع (references) are strong websites of big advertisers (ad running 90+ days, 90+ active ads), USA by default, sorted by how long the ad has run, used for inspiration. عملائي (my clients) are small local advertisers (under 15 ads, ad running 7+ days, Instagram 1,000–70,000 followers) with no website or a very weak one, from the country the user names, with Instagram, followers, WhatsApp, email and where the lead was found. Self-contained (needs no other skill). Use when the user says "الباحث", "الكشاف", "شغّل الكشاف", "scout", "أبي مراجع", "بدي مراجع", "أبي عملاء", "بدي عملاء", "دور لي عملاء", "دور لي مراجع", "researcher", "find references", or "find clients from ad library".
---

# الباحث (al-bahith)

Source: **Meta Ad Library only**. Talk to the user in Arabic (Gulf/Levantine, plain words).
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
