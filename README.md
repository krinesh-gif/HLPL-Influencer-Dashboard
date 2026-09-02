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

- **Collabs** — the register. Locked price, payment state, box contents, shipment stage.
- **Ship queue** — supply's working view. Select ready rows → **Build UC bulk file** → upload in Unicommerce → **Paste dispatch details** to close the loop.
- **Content** — post date, link, views, reach, likes, comments, shares, saves; ER, CPV and CPE computed.
- **Influencers** — the master. Address, pincode, mobile, tier, category, full collab history, one-click repeat.
- **Products** — the SKU master, pasted straight from the UC item master, so a bulk upload can never fail on a typed SKU.
- **Analytics** — influencers locked per month, budget locked, paid vs open, spend by tier, live pipeline, median request→dispatch TAT, cheapest views bought.
- **Setup** — channel, facility, order prefix, gifting treatment, and the Unicommerce column mapping.

## The Unicommerce bulk file

`templates/unicommerce-bulk-order-template.csv` — the real 73-column sale-order
import header, headers verbatim including the `*` on mandatory columns.
`templates/unicommerce-bulk-order-sample.csv` — two orders, one of them with two SKUs.

The five mandatory columns are always filled:

| Column | Filled with |
|---|---|
| `Sales Order Code*` | `PR-YYMM-001`, written back onto the collab row |
| `COD*` | `0` — every gifting order is prepaid |
| `Sale Order Item Code*` | the order code plus the line number, e.g. `PR-2609-001-2` |
| `Shipping Method*` | the value set in Setup; the export is blocked while it is blank |
| `Item SKU Code*` | picked from the SKU master, never typed |

Other rules the generator follows:

- **One row per item.** An order with two SKUs writes two rows sharing the same
  Sales Order Code and carrying different Sale Order Item Codes.
- **Gifting treatment** (Setup): Selling Price = MRP and Discount = MRP, so the box
  carries its real value on the invoice while Prepaid Amount comes out ₹0. Switch to
  *Charge MRP* if you ever bill a shipment.
- **Payment Mode** `PREPAID`, **Currency Code** `INR`, both settable in Setup.
- **Item Tag** carries the box type, the deliverable and the creator's handle, so the
  packing team can see what it is without opening the dashboard.
- **State names come from a dropdown**, pincodes are forced to 6 digits and mobiles to
  10 — the three things that make UC reject a bulk file.

Columns are remappable under **Setup → Unicommerce column mapping** if your template
changes; **Reset to the UC template** puts back the 73 columns above.

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
