# Website score (approved by the user, 2026-11-09)

10 criteria, one point each. Strong = 7–10. Middle = 5–6. Very weak = 0–4.

## Counts as "no website" (no scoring needed)
- The only link goes to WhatsApp, Instagram, Facebook or a link hub (Linktree and similar).
- The site does not load: expired domain, security error, empty page, or a bot wall even in the browser.
`site_check.py` + `shots.py` decide this. `write_xlsx.py` applies it.

## Set by script (Claude does not score these)
- **c1** Mobile speed: the main content of the first screen appears in **under 3 seconds** on a phone with normal internet (Largest Contentful Paint, measured by `shots.py` → `load_seconds`). The user chose this rule on 2026-11-09 instead of Lighthouse, which was too harsh. A slow site gets the problem "الموقع ياخذ X ثانية يفتح على الجوال" added automatically.
- **c9** Tracking: Meta Pixel or Google Analytics/GTM found in the HTML.

## Scored by Claude from the screenshots (`<id>_m1.jpg` mobile first screen, `<id>_m2.jpg` mobile scroll, `<id>_d1.jpg` desktop)
Score 1 = pass, 0 = fail. Be strict and the same every time. When unsure, give 0.

| Key | Criterion | Pass (1) when… | Fail (0) when… |
|---|---|---|---|
| c2 | Clean on mobile | Nothing cut off or overlapping, readable text size, no sideways scroll, menu works on a phone | Desktop layout squeezed, tiny text, broken overlaps, popups covering everything |
| c3 | First screen is clear | In 3 seconds you know what they sell (headline or product clearly visible) | Only a logo or slider, vague slogan, nothing visible about the product |
| c4 | Clear call-to-action button | A strong button on the first mobile screen (Shop now / Book / Order / Contact) | No button, or only a small link, or the button only appears far down |
| c5 | Custom design | Their own brand look: their own colours, fonts and layout | A stock Salla/Zid/Shopify/Wix theme with default sections, or a generic builder page |
| c6 | Professional photos | Sharp, well-lit, consistent product or lifestyle photos | Blurry or phone snaps, mixed styles, stretched or watermarked images |
| c7 | Trust signals | Reviews, star ratings, testimonials, guarantee, "as seen in" or partner logos visible | None visible in the 3 screenshots |
| c8 | Ordering works | A cart, product pages with a price and add-to-cart, a booking widget or a contact form | Only "message us on WhatsApp/Instagram", or no way to buy or book on the site |
| c10 | Clean text and core pages | Clear copy without obvious mistakes; the menu shows about/products/contact (or similar) | Broken or placeholder text ("Lorem ipsum"), many mistakes, missing basic pages |

## scores.json format (one entry per scored page_id)
```json
{
  "1234567890": {
    "c2": 1, "c3": 1, "c4": 0, "c5": 1, "c6": 1, "c7": 0, "c8": 1, "c10": 1,
    "problems": ["ما فيه زر طلب بأول شاشة", "ما فيه تقييمات أو آراء عملاء", "الموقع بطيء على الجوال"],
    "why_strong": "تصميم خاص، صور احترافية، سلة شغالة"
  }
}
```
- `problems`: the 3 biggest visual or content weaknesses, in short Gulf Arabic. They are used in the user's outreach message, so make them concrete and fixable. Do not write about speed: the script adds that itself.
- `why_strong`: only when the site looks strong. One line in Arabic.
- The final score is computed by `write_xlsx.py`. If the load time is unknown, the score is scaled from the criteria that are known, and the row says so.
