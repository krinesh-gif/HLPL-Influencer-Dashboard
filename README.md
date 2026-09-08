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

- **New shipment** — the whole job on one page. Paste the address, paste the products in
  your team's own words, download the Unicommerce file. Save several before downloading
  and they come out as one file.
- **Collabs** — the register. Locked price, payment state, box contents, shipment stage.
- **Ship queue** — supply's working view. Select ready rows → **Build UC bulk file** → upload in Unicommerce → **Paste dispatch details** to close the loop.
- **Content** — post date, link, views, reach, likes, comments, shares, saves; ER, CPV and CPE computed.
- **Influencers** — the master. Address, pincode, mobile, tier, category, full collab history, one-click repeat.
- **Products** — the SKU master, pasted straight from the UC item master, so a bulk upload can never fail on a typed SKU.
- **Analytics** — influencers locked per month, budget locked, paid vs open, spend by tier, live pipeline, median request→dispatch TAT, cheapest views bought.
- **Setup** — channel, facility, order prefix, gifting treatment, and the Unicommerce column mapping.

## The Unicommerce bulk file

Built to match a sale-order file the team actually uploaded successfully, rather
than a guess at the template — same 71 columns, same values, same conventions.

`templates/unicommerce-bulk-order-template.csv` — the header row.
`templates/unicommerce-bulk-order-sample.csv` — two orders of three products each.

| Column | Filled with |
|---|---|
| `Sales Order Code*` | the running series, `PR632`, `PR633`, … continuing from the last used |
| `Display Sales Order Code` | the same code |
| `COD*` | `0` — every gifting order is prepaid |
| `Channel` | `PR` |
| `Shipping Method*` | `STD` |
| `Shipping / Billing Address Id` | `SENSE` |
| `Sale Order Item Code*` | the SKU code itself |
| `Item SKU Code*` | from the SKU master, never typed |
| `Selling Price` | the SKU's MRP where one is recorded, else blank |
| `Quantity` | blank when 1, the number when more |

Prefix, next number, channel, shipping method and address id are all editable
under **Setup**.

Other rules:

- **One row per item.** Five products in one order write five rows. Every column is
  identical across them except `Item SKU Code*` (AJ) and `Sale Order Item Code*` (AH),
  which carry the SKU code.
- **No byte-order mark, CRLF line endings** — as in the working file.
- **State names come from a dropdown**, pincodes are forced to 6 digits and mobiles to
  10 — the three things that make UC reject a bulk file.

Columns are remappable under **Setup → Unicommerce column mapping**; **Reset to the UC
template** puts back the 71 above.

## Running it

`index.html` is the whole application — no build step, no framework. It picks its
data source at load, in this order:

1. **Claude artifact** — when opened inside the Claude viewer, it uses the artifact's
   own database, plus AI creator screening and file downloads.
2. **Neon** — when served from your own deployment, it talks to `/api/data`, which
   reads and writes a Neon Postgres database.
3. **Neither** — everything is kept in that browser alone. The page says so plainly
   rather than pretending to be shared.

Setup → **Connection details** reports which of the three is in play and why.

## Deploying to Vercel with Neon

The page is public, so it can never hold the database credentials. `api/data.js` is a
serverless function that holds them instead and checks a shared team code first.

1. **Create a Neon project** at neon.tech and copy the connection string. Pick the
   region nearest your team — Singapore or Mumbai for India.
2. **In Vercel → Settings → Environment Variables**, add:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | the Neon connection string |
   | `TEAM_CODE` | any phrase your two teams will type once |

3. **Redeploy.** The table is created on the first request, so there is no migration
   to run:

   ```sql
   CREATE TABLE docs (
     collection  text        NOT NULL,
     id          text        NOT NULL,
     data        jsonb       NOT NULL,
     updated_at  timestamptz NOT NULL DEFAULT now(),
     PRIMARY KEY (collection, id)
   );
   ```

4. **Open the URL and enter the team code.** It is remembered per device, so each
   person types it once.

Collabs, influencers, SKUs and settings are rows in that one table, keyed by
collection and id. The page re-reads every 7 seconds while the tab is visible, so
supply sees a new request within seconds of marketing saving it — near-live rather
than instant, which is what this workflow needs.

**Without `TEAM_CODE` set, the API is open to anyone with the URL.** Set it.

### What the Neon deployment does not have

AI creator screening and the one-click file save are granted by the Claude viewer, so
they are absent on your own domain. The engagement maths in the screening drawer
still runs, and the UC bulk file falls back to an ordinary browser download.
