# Al-Bahith (الباحث / الكشاف) — Meta Ad Library lead & reference finder for Claude Code

A Claude Code skill that searches **Meta Ad Library** for active ads and gives you one of two tables:

- **المراجع (References):** big advertisers with strong websites, for inspiration. Their ad has run 90+ days and they have more than 90 active ads. USA by default, sorted by how long the ad has run.
- **عملائي (My clients):** small local advertisers that need a website: fewer than 15 active ads, an ad running 7+ days, Instagram with 1,000–70,000 followers, and no website or a very weak one. You get the name, Instagram link, followers, website yes/no, WhatsApp, email and the Ad Library link where you found them.

Everything goes into **one Excel file** (`الباحث.xlsx`). Each run adds to it, never repeats a page, and keeps المراجع sorted by days running.

## How it works
1. You say what you want ("أبي عملاء بالكويت مجال عيادات" or "أبي مراجع"). Claude proposes search keywords and waits for your OK.
2. A background script scans Ad Library: the active ad count, the oldest ad date, plus the Instagram handle, followers and the country the page is managed from (from Ad Library's own "About" panel, with no Instagram login).
3. Clients only: it reads each Instagram bio for WhatsApp numbers, emails and the website link, using **your own** saved Instagram session, paced slowly.
4. Websites are checked (loads? Meta Pixel / Google Analytics?) and screenshotted on mobile and desktop. Mobile load time is measured: under 3 s passes.
5. Claude scores each site on 10 points (`references/site-score.md`). 7–10 is strong (a reference), 5–6 is middle, 0–4 is very weak (a client).
6. The rows are added to the Excel file. Clients mode also fills two side sheets: «شيك عليها» (strong sites found while looking for clients) and «وسط» (middle).

### Second source: Instagram (phone mode)
Ask for clients "from Instagram" (or when Ad Library is blocked). The skill opens Instagram as an **iPhone** (phone screen and User-Agent) with your own saved session, where keyword search ("perfume kuwait") and hashtag pages (#عطور_الكويت) show posts the way the app does. Then:
- It collects every account that posted, plus every shop **tagged** in their captions. Shops that pay influencers already spend on marketing, so they're read first.
- It reads each profile, paced slowly: followers, bio and links, plus the **Contact button** data (email, phone, WhatsApp the business set in the app, often not in the bio).
- It keeps local businesses only (1,000–70,000 followers, not influencers, a local phone or a sign of the country).

### "No website" mode
Ask for clients **with no website** ("عملاء بدون موقع"). Every bio link is checked live, and any business with a working website is skipped. Only shops with no site (or only WhatsApp / Linktree-type links, or a dead site) go into the table, and the number you ask for counts only those.
Real test (perfume, Kuwait): 536 accounts found in 5 minutes; 180 profiles read gave 28 shops with no website, 25 of them with WhatsApp and 12 with email.

A full Ad Library run of 50 clients takes about 20–30 minutes, mostly the paced Instagram reading. 20 references take about 10–15 minutes.

## Requirements
- Claude Code
- Python 3.11+ (`python` on Windows, `python3` on Mac)
- Python packages:
  ```
  pip install "scrapling[fetchers]" openpyxl
  scrapling install
  ```

## Install
Paste this into Claude Code:

```
Install the Al-Bahith skill from https://github.com/jameellzx/al-bahith-skill:
copy the "al-bahith" folder into my user skills folder (~/.claude/skills/al-bahith).
Then install what it needs: pip install "scrapling[fetchers]" openpyxl, then run "scrapling install".
Check it works with: python ~/.claude/skills/al-bahith/scripts/paths.py
When I first ask for clients, run the Instagram login (scripts/ig_profile.py --login) and wait for me to sign in myself.
```

Start a new session and say **"الكشاف"**, **"أبي عملاء"**, **"أبي مراجع"**, or **"أبي ٥٠ عميل بدون موقع من الانستقرام، مجال عطور، الكويت"**.

## Your data
Everything is stored in `~/al-bahith/`:
- `الباحث.xlsx`: the one Excel file
- `seen.json`: pages already shown, so they never repeat
- `ig_state/`: your Instagram session
- `runs/`: working files and screenshots

To use another folder, create `~/.claude/skills/al-bahith/config.json` with `{"data_dir": "D:/my-folder"}`, or set the env `AL_BAHITH_DATA`.

## Be careful
- Sign in to Instagram **yourself** in the window the script opens. Claude never types your password. A second account is safer than your main one.
- Ad Library and Instagram slow down or block heavy use. Keep runs small, keep the default pacing, and only collect public contact details.
- Scraping may break Meta's or Instagram's terms. Use it at your own risk.
- If Meta changes its pages, a script can break. The skill tells Claude to report it and try a quick fix first.

## Files
```
al-bahith/
  SKILL.md                       the workflow: modes, rules, steps
  references/site-score.md       the 10-point website score
  references/keywords-all-fields.md   keyword lists (Gulf Arabic/English, USA)
  scripts/adlib_scan.py          Ad Library scan (stealth browser, parallel)
  scripts/ig_profile.py          Instagram bio + Contact button data with your saved session
  scripts/ig_search.py           Instagram keyword/hashtag search in phone mode -> leads (--no-site)
  scripts/site_check.py          site loads? pixel? WhatsApp/email on the page
  scripts/shots.py               mobile + desktop screenshots, mobile load time
  scripts/write_xlsx.py          sorts pages into tables, adds them to the one Excel file
  scripts/seen.py                no-repeat memory
  scripts/paths.py               where the data lives
```
