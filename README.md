# HLPL Collab

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

- **New shipment** — marketing's page. Paste the address, add the products either by
  pasting a list or searching the catalogue, save. There is no download here on purpose:
  entries pile up through the day and supply takes them as one file the next morning.
- **Ship queue** — supply's page. Three one-click downloads of the same ready batch:
  **Unicommerce** (CSV, per item), **Selloship** (xlsx, per parcel) and **Shipway**
  (CSV, per item). Each saves the file and marks the orders created. *Review first*
  opens the batch for checking before downloading.
- **Collabs** — the register. Locked price, payment state, box contents, shipment stage.
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

## The Selloship file

Selloship is a courier aggregator, so its unit is the parcel: **one row per order**,
where Unicommerce writes one row per item. `templates/selloship-bulk-order-sample.xlsx`
is a generated example.

| Column | Filled with |
|---|---|
| `product_name` | every product in the box, joined with ` + ` |
| `sku` | the SKU codes, joined with ` \| ` |
| `qty` | total units in the parcel |
| `price` / `old_price` | the box value at MRP, or the fallback declared value |
| `first_name` / `last_name` | the consignee name split; `.` when there is no surname |
| `address` / `landmark` | address line 1, and line 2 as the landmark |
| `payment_method` | `4` (prepaid) |
| `alt_mobile_no` | the same number as `mobile_no` — Selloship rejects it blank |
| `custom_order_id` | the same `PR632` code the Unicommerce file uses |
| `L` / `B` / `H` | the dimensions set per box type |

Declared value, payment method and the dimensions for each box type are set under
**Setup → Selloship defaults**. Couriers reject a zero-value parcel, so when the SKUs
carry no MRP the fallback value is used.

The workbook is built in the browser with SheetJS from the CDN; if that script cannot
load, the same columns are saved as CSV rather than nothing.

## The Shipway file

`templates/shipway-bulk-order-sample.csv` — two orders, three item rows. Built to the
38 columns of Shipway's own sample import, one row per item like Unicommerce.

Order Total Amount is derived the way their sample does it, verified against every row
of it: `(price − product discount) × qty + shipping − order discount`.

| Column | Filled with |
|---|---|
| `*Order ID` | the same `PR632` code the other two files use |
| `Order Tags` | the box type |
| `*Product Price` | the SKU's MRP, or the declared value split across the units |
| `*Order Total Amount` | price × quantity |
| `*Payment Type` | `P` prepaid (`C` if the payment method is switched to COD) |
| `*Order Date` | `[YYYY-MM-DD]`, brackets included, as in their sample |
| `*Order Dead Weight(g)`, `*Length/Breadth/Height` | the box type's weight and size |
| `*Shipping:FirstName` / `LastName` | the consignee name split; `.` with no surname |
| `*Shipping:Email` | the creator's email, else the fallback email |

Weight, dimensions, warehouse ID, declared value and fallback email are all under
**Setup → Courier file defaults**. Shipway marks the email column mandatory, so the
download warns before building a file with any blank ones.

## Who may do what

With `MARKETING_CODE` set, the code someone types decides what they can do, and the
API enforces it rather than the page merely hiding buttons:

| | Marketing | Supply |
|---|---|---|
| Add and edit shipments | yes | yes |
| Move a shipment past *Ready to Ship* | no | yes |
| Download a courier file | no | yes |
| Write order codes, AWB, courier, dispatch dates | no | yes |
| Change Setup | no | yes |

A marketing save that omits an order code or tracking keeps what is already stored
rather than clearing it, and an order that has already gone to the courier is closed
to marketing entirely. Leave `MARKETING_CODE` unset and everyone who gets in has
supply's rights, as before.

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
   | `TEAM_CODE` | supply's code — full rights |
   | `MARKETING_CODE` | optional, marketing's code — may raise shipments only |

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

## The Unicommerce live link

With four more variables set, supply stops downloading a file at all. `api/uni.js`
creates the sale orders over Uniware's REST API and reads the tracking number back,
so the collab team never has to ask where a box is.

| Name | Value |
|---|---|
| `UNI_TENANT` | the subdomain only, e.g. `aravi` for `aravi.unicommerce.com` |
| `UNI_USERNAME` | a Uniware user with **Admin** rights on the facility |
| `UNI_PASSWORD` | that user's password |
| `UNI_FACILITY` | the facility code the PR boxes ship from |
| `CRON_SECRET` | needed only for the scheduled run; Vercel sends it automatically |

Leave any of the first four unset and the link simply does not appear — the files
keep working. The login never reaches the browser: it is read inside the function,
and the access token is cached in a `secret` row that `api/data.js` does not serve.

**What it does**

| Step | Endpoint | Result |
|---|---|---|
| Create | `POST /services/rest/v1/oms/saleOrder/create` | the order appears in the PR channel, and `ucCode` is written back |
| Read back | `POST /services/rest/v1/oms/saleorder/get` | `trackingNumber` → AWB, `shippingProvider` → courier, `dispatched` / `delivered` → the dates and the stage |
| Log in | `GET /oauth/token` | cached for its full life, refetched once on a 401 |

Two switches live in Setup → Unicommerce live link:

- **Create orders automatically** — off by default, which keeps the rule that only
  supply creates orders. On, the scheduled run creates every address-clean
  Ready-to-Ship row by itself.
- **Keep tracking up to date** — on by default. While anyone has the Ship queue
  open, the AWB is re-read every few minutes.

`vercel.json` schedules `/api/uni?op=autorun` once a day at 08:40 IST. On a Hobby
plan that daily slot is the most Vercel allows; on Pro, change the schedule to
`*/30 * * * *` for a half-hourly run.

**Before the first live push**, use **Show what would be sent** in Setup. It builds
the real payload and sends nothing, so the channel, the address and the SKU codes can
be checked against a Uniware order that is known to work. Orders go out one at a
time, so a row Uniware refuses is reported on that row and the rest still go —
unlike a CSV, where one bad state name rejects the whole file.

Three details worth knowing:

- `thirdPartyShipping` is sent as `false` so Uniware allocates the courier and
  generates the AWB. With `true` there would be no tracking number to read back.
- The API has no quantity field, so a quantity of 2 becomes two sale-order items.
- If a number in the `PR…` series is already taken in Uniware — likely, after years
  of manual uploads — the push steps to the next free one rather than failing.

### What the Neon deployment does not have

AI creator screening and the one-click file save are granted by the Claude viewer, so
they are absent on your own domain. The engagement maths in the screening drawer
still runs, and the UC bulk file falls back to an ordinary browser download.
