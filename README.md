# Reel → Doorstep

A single-page dashboard that replaces the WhatsApp group between the influencer
marketing team and the supply team at Hivefy Lifestyle (Aravi Organic).

One row per collab. Marketing fills the top half, supply fills the bottom half,
and the Unicommerce bulk-order file is generated from the same row — nobody
retypes an address, a SKU or a tracking number.

## The flow it replaces

| Today | With this board |
|---|---|
| Marketing posts address + products in the WhatsApp group | Marketing saves a collab row; address comes from the influencer master |
| Supply copies it into a UC bulk sheet by hand | Supply ticks the ready rows and downloads the UC file |
| Supply creates orders in UC one by one | One bulk upload, order codes written back automatically |
| Dispatch details typed into a shared Excel | Paste the UC dispatch export back in; rows update themselves |
| "Can you resend her address?" | The influencer master already has it — hit **Repeat** |

## Screens

- **Collabs** — the register. Locked price, payment state, T&C-on-mail state, box contents, shipment stage.
- **Ship queue** — supply's working view. Select ready rows → **Build UC bulk file** → upload in Unicommerce → **Paste dispatch details** to close the loop.
- **Content** — post date, link, views, reach, likes, comments, shares, saves; ER, CPV and CPE computed.
- **Influencers** — the master. Address, pincode, mobile, tier, category, full collab history, one-click repeat.
- **Products** — the SKU master, pasted straight from the UC item master, so a bulk upload can never fail on a typed SKU.
- **Analytics** — influencers locked per month, budget locked, paid vs open, spend by tier, live pipeline, median request→dispatch TAT, cheapest views bought.
- **Setup** — channel, facility, order prefix, gifting treatment, and the Unicommerce column mapping.

## The Unicommerce bulk file

`templates/unicommerce-bulk-order-template.csv` — headers only.
`templates/unicommerce-bulk-order-sample.csv` — one two-line order, filled in.

Rules the generator follows:

- **One row per item.** An order with two SKUs writes two rows that share the same
  Sale Order Code — that is how UC groups them into a single order.
- **Order codes** come out as `PR-YYMM-001` and are written back onto the collab row,
  so the AWB you paste back later lands on the right influencer.
- **Gifting treatment** (Setup): selling price = MRP and discount = MRP, so the box
  carries its real value on the invoice while the order settles at ₹0. Switch to
  *Charge MRP* if you ever bill a shipment.
- **State names come from a dropdown**, pincodes are forced to 6 digits and mobiles to
  10 — the three things that make UC reject a bulk file.

> The default column set follows the standard Unicommerce sale-order import layout, but
> the exact template differs by tenant. Download your own template from
> Unicommerce, copy row 1, and paste it into **Setup → Paste your UC header row**.
> Your headers are kept verbatim and each one is matched to a field automatically.

## Running it

`index.html` is the whole application — no build step, no dependencies.

Published as a Claude Artifact it stores data server-side and both teams see each
other's changes live. Opened as a plain local file it falls back to browser storage,
which is per-person and not shared — useful for a look, not for running the programme.
