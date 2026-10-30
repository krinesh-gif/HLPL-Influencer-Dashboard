/*
 * HLPL Collab — Unicommerce (Uniware) integration.
 *
 * Two jobs, both of which used to be done by hand:
 *
 *   push  — turn "Ready to Ship" rows into sale orders in the PR channel,
 *           so nobody downloads a CSV and uploads it again.
 *   sync  — read the tracking number and courier back off those orders, so
 *           the collab team stops asking supply where the box is.
 *
 * The page is static and shared by two teams, so the Uniware login never
 * goes near the browser. It lives only in this function's environment.
 *
 * Environment variables (Vercel → Settings → Environment Variables):
 *   UNI_TENANT     the subdomain only, e.g. "aravi" for aravi.unicommerce.com.
 *                  A full URL works too.
 *   UNI_USERNAME   a Uniware user with Admin rights on the facility.
 *   UNI_PASSWORD   that user's password.
 *   UNI_FACILITY   the facility code the PR boxes ship from.
 *   CRON_SECRET    optional. Lets Vercel's scheduler call this without a
 *                  team code. Vercel sends it as "Authorization: Bearer …".
 *
 * Everything else (channel, shipping method, order-code series) is read from
 * the board's own Setup, so the API sends exactly what the CSV would have.
 *
 * Uniware reference:
 *   GET  /oauth/token?grant_type=password&client_id=my-trusted-client&…
 *   POST /services/rest/v1/oms/saleOrder/create
 *   POST /services/rest/v1/oms/saleorder/get
 */
import { neon } from "@neondatabase/serverless";

const TOKEN_ROW = { collection: "secret", id: "uniToken" };
const STATE_ROW = { collection: "secret", id: "uniState" };
const SYNC_BATCH = 40;          // sale orders read per sync run
const PUSH_BATCH = 25;          // orders created per push run
const CALL_TIMEOUT = 20000;

const bad = (res, code, error) => res.status(code).json({ error });

/* ---------------------------------------------------------------- helpers */

const digits = (s) => String(s ?? "").replace(/\D/g, "");
const phone10 = (s) => {
  const d = digits(s);
  return d.length > 10 ? d.slice(-10) : d;
};
const num = (v) => {
  const n = parseFloat(String(v ?? "").replace(/[^0-9.\-]/g, ""));
  return isFinite(n) ? n : 0;
};

/* The business runs on IST, so a dispatch at 11pm must not read as the next
   day. Uniware hands these back as epoch milliseconds. */
const IST_MS = 5.5 * 3600 * 1000;
const istDate = (ms) => {
  const n = Number(ms);
  if (!n || !isFinite(n)) return "";
  return new Date(n + IST_MS).toISOString().slice(0, 10);
};

function tenantBase() {
  const raw = String(process.env.UNI_TENANT || "").trim().replace(/^\/+|\/+$/g, "");
  if (!raw) return "";
  if (/^https?:\/\//i.test(raw)) return raw.replace(/\/+$/, "");
  /* A whole hostname is as likely to be pasted in as the tenant name alone,
     so "hivefylifestyle.unicommerce.co.in" must not get the domain added
     again. This is also the only way to reach a tenant on a domain other
     than the default below. */
  if (raw.includes(".")) return "https://" + raw;
  /* Indian tenants are served from unicommerce.co.in, not .com. */
  return "https://" + raw + ".unicommerce.co.in";
}

function missingConfig() {
  const gaps = [];
  if (!process.env.UNI_TENANT) gaps.push("UNI_TENANT");
  if (!process.env.UNI_USERNAME) gaps.push("UNI_USERNAME");
  if (!process.env.UNI_PASSWORD) gaps.push("UNI_PASSWORD");
  if (!process.env.UNI_FACILITY) gaps.push("UNI_FACILITY");
  return gaps;
}

async function jsonCall(url, init) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), CALL_TIMEOUT);
  try {
    const r = await fetch(url, { ...init, signal: ctl.signal });
    const text = await r.text();
    let body = null;
    try { body = text ? JSON.parse(text) : null; } catch { /* not JSON */ }
    return { status: r.status, ok: r.ok, body, text };
  } catch (e) {
    const why = e && e.name === "AbortError"
      ? "Unicommerce did not answer in time."
      : "Could not reach Unicommerce.";
    return { status: 0, ok: false, body: null, text: why };
  } finally {
    clearTimeout(timer);
  }
}

/* ------------------------------------------------------------ token cache */

/* The access token is good for about eleven hours. This function is
   serverless and forgets everything between calls, so the token is parked in
   a row no client can read: "secret" is not a collection /api/data serves. */
async function readRow(sql, { collection, id }) {
  const rows = await sql`SELECT data FROM docs WHERE collection = ${collection} AND id = ${id}`;
  return rows.length ? rows[0].data : null;
}
async function writeRow(sql, { collection, id }, data) {
  await sql`
    INSERT INTO docs (collection, id, data, updated_at)
    VALUES (${collection}, ${id}, ${JSON.stringify(data)}::jsonb, now())
    ON CONFLICT (collection, id)
    DO UPDATE SET data = EXCLUDED.data, updated_at = now()`;
}

async function fetchToken(base) {
  const q = new URLSearchParams({
    grant_type: "password",
    client_id: "my-trusted-client",
    username: process.env.UNI_USERNAME || "",
    password: process.env.UNI_PASSWORD || "",
  });
  /* The documented call puts the login in the query string. Some tenants are
     set up to take it in headers instead, so that is the fallback. */
  let r = await jsonCall(base + "/oauth/token?" + q.toString(), {
    method: "GET", headers: { "content-type": "application/json" },
  });
  if (!r.ok || !r.body || !r.body.access_token) {
    const headerQ = new URLSearchParams({ grant_type: "password", client_id: "my-trusted-client" });
    const alt = await jsonCall(base + "/oauth/token?" + headerQ.toString(), {
      method: "GET",
      headers: {
        "content-type": "application/json",
        username: process.env.UNI_USERNAME || "",
        password: process.env.UNI_PASSWORD || "",
      },
    });
    if (alt.ok && alt.body && alt.body.access_token) r = alt;
  }
  if (!r.ok || !r.body || !r.body.access_token) {
    const host = base.replace(/^https?:\/\//, "");
    const said = (r.body && (r.body.error_description || r.body.error)) || "";
    /* Uniware answers a bad password in JSON. Anything else — an HTML page, a
       proxy's "upstream connect error" — means the call never reached the
       Uniware application, which is nearly always the wrong hostname. */
    if (said) throw new Error("Unicommerce refused the login at " + host + ": " + said);
    if (!r.status) throw new Error(
      "Could not reach " + host + " at all. " + r.text +
      " Check UNI_TENANT is the exact subdomain your team signs in to.");
    throw new Error(
      "Nothing answered as Uniware at " + host + " (HTTP " + (r.status || "no reply") + "). " +
      "Check UNI_TENANT is the exact subdomain your team signs in to, and that Unicommerce " +
      "has enabled API access for this account. It replied: " +
      (String(r.text || "").replace(/\s+/g, " ").slice(0, 160) || "nothing"));
  }
  return {
    token: r.body.access_token,
    /* Expire it a few minutes early rather than discover it mid-push. */
    expiresAt: Date.now() + Math.max(60, num(r.body.expires_in) - 300) * 1000,
  };
}

async function accessToken(sql, base, force) {
  if (!force) {
    const cached = await readRow(sql, TOKEN_ROW);
    if (cached && cached.token && num(cached.expiresAt) > Date.now()) return cached.token;
  }
  const fresh = await fetchToken(base);
  await writeRow(sql, TOKEN_ROW, fresh);
  return fresh.token;
}

/* One retry on 401: a token can be revoked at the Uniware end before it
   expires, and the whole run should not fail for that. */
async function uniPost(sql, base, path, payload) {
  for (const force of [false, true]) {
    const token = await accessToken(sql, base, force);
    const r = await jsonCall(base + path, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        Authorization: "bearer " + token,
        Facility: process.env.UNI_FACILITY || "",
      },
      body: JSON.stringify(payload),
    });
    if (r.status === 401 && !force) continue;
    return r;
  }
}

function uniErrors(r) {
  if (r.status === 0) return r.text;
  const b = r.body;
  if (b && Array.isArray(b.errors) && b.errors.length) {
    return b.errors.map((e) => (e && (e.message || e.description || e.code)) || String(e)).join("; ");
  }
  if (b && b.message) return String(b.message);
  if (!r.ok) return "Unicommerce replied " + r.status + ". " + String(r.text || "").slice(0, 160);
  return "";
}

/* --------------------------------------------------- building a sale order */

function orderCodeMaker(settings, collabs) {
  const pfx = String(settings.orderPrefix || "PR").toUpperCase();
  const re = new RegExp("^" + pfx + "(\\d+)$", "i");
  let max = num(settings.orderNextNo) ? num(settings.orderNextNo) - 1 : 0;
  for (const c of collabs) {
    const m = re.exec(String(c.ucCode || "").trim());
    if (m) max = Math.max(max, +m[1]);
  }
  let n = 0;
  return () => pfx + (max + ++n);
}

/* Mirrors the CSV builder: a gifted box carries the MRP as both price and
   discount so the order totals nothing, and quantity becomes one sale-order
   item per unit, because the API has no quantity field. */
function saleOrderPayload(collab, code, settings, skuByCode) {
  const st = collab.ship || {};
  const gifting = !!settings.gifting;
  const addrId = String(settings.addressId || "ADDR1");
  const items = [];
  let discount = 0;

  for (const raw of collab.items || []) {
    const sku = skuByCode[String(raw.sku || "").toUpperCase()] || {};
    const mrp = num(raw.mrp) || num(sku.mrp);
    const sellingPrice = mrp;
    const lineDiscount = gifting ? mrp : 0;
    const qty = Math.max(1, Math.round(num(raw.qty) || 1));
    for (let u = 0; u < qty; u++) {
      items.push({
        code: code + "-" + (items.length + 1),
        itemSku: String(raw.sku || ""),
        shippingMethodCode: settings.shipMethod || "STD",
        packetNumber: 1,
        giftWrap: false,
        facilityCode: "",
        sellingPrice,
        discount: lineDiscount,
        totalPrice: Math.max(0, sellingPrice - lineDiscount),
        prepaidAmount: 0,
        shippingCharges: 0,
      });
      discount += lineDiscount;
    }
  }

  const notes = [collab.box, collab.deliverable, collab.notes]
    .filter(Boolean).join(" | ").slice(0, 500);

  return {
    saleOrder: {
      code,
      displayOrderCode: code,
      displayOrderDateTime: new Date().toISOString(),
      channel: settings.channel || "PR",
      customerName: String(st.name || "").slice(0, 100),
      notificationEmail: String(st.email || settings.fallbackEmail || "").slice(0, 100),
      notificationMobile: phone10(st.phone),
      cashOnDelivery: false,
      paymentInstrument: "CASH",
      /* False means Uniware allocates the courier and generates the AWB —
         which is the whole point: there is nothing to read back otherwise. */
      thirdPartyShipping: false,
      currencyCode: settings.currency || "INR",
      additionalInfo: notes,
      addresses: [{
        id: addrId,
        name: String(st.name || "").slice(0, 100),
        addressLine1: String(st.addr1 || "").slice(0, 500),
        addressLine2: String(st.addr2 || "").slice(0, 500),
        city: String(st.city || "").slice(0, 100),
        state: String(st.state || "").slice(0, 45),
        country: settings.country || "India",
        pincode: digits(st.pin),
        phone: phone10(st.phone),
        email: String(st.email || settings.fallbackEmail || "").slice(0, 100),
      }],
      billingAddress: { referenceId: addrId },
      shippingAddress: { referenceId: addrId },
      saleOrderItems: items,
      totalDiscount: discount,
      totalShippingCharges: num(settings.shippingCharge),
      totalCashOnDeliveryCharges: 0,
      totalPrepaidAmount: 0,
      totalStoreCredit: 0,
    },
  };
}

/* The same gates the page shows, repeated here so a scheduled push cannot
   send a half-filled row that Uniware would reject for the whole file. */
function rowProblems(collab) {
  const st = collab.ship || {};
  const out = [];
  if (!String(st.name || "").trim()) out.push("name is missing");
  if (String(st.addr1 || "").trim().length < 6) out.push("address line 1 is missing or too short");
  if (!String(st.city || "").trim()) out.push("city is missing");
  if (!String(st.state || "").trim()) out.push("state is missing");
  if (digits(st.pin).length !== 6) out.push("pincode is not 6 digits");
  if (phone10(st.phone).length !== 10) out.push("mobile is not 10 digits");
  if (!(collab.items || []).length) out.push("no products on the row");
  else if ((collab.items || []).some((i) => !String(i.sku || "").trim())) out.push("a product has no SKU code");
  return out;
}

/* ------------------------------------------------------------- board reads */

async function loadBoard(sql) {
  const rows = await sql`SELECT collection, id, data FROM docs WHERE collection IN ('collabs','skus','config')`;
  const collabs = [], skuByCode = {};
  let settings = {};
  for (const r of rows) {
    if (r.collection === "collabs") collabs.push({ id: r.id, ...r.data });
    else if (r.collection === "skus") {
      const code = String((r.data || {}).code || "").toUpperCase();
      if (code) skuByCode[code] = r.data;
    } else if (r.collection === "config" && r.id === "settings") settings = r.data || {};
  }
  return { collabs, skuByCode, settings };
}

async function saveCollab(sql, id, patch) {
  await sql`
    UPDATE docs SET data = data || ${JSON.stringify(patch)}::jsonb, updated_at = now()
    WHERE collection = 'collabs' AND id = ${id}`;
}

/* ------------------------------------------------------------------- push */

async function doPush(sql, base, ids, { dryRun }) {
  const { collabs, skuByCode, settings } = await loadBoard(sql);
  const byId = new Map(collabs.map((c) => [c.id, c]));

  let chosen = Array.isArray(ids) && ids.length
    ? ids.map((id) => byId.get(id)).filter(Boolean)
    : collabs.filter((c) => c.shipStatus === "Ready to Ship");

  const skipped = [];
  const queue = [];
  for (const c of chosen) {
    if (c.ucCode) { skipped.push({ id: c.id, name: (c.ship || {}).name || "", why: "already in Unicommerce as " + c.ucCode }); continue; }
    const probs = rowProblems(c);
    if (probs.length) { skipped.push({ id: c.id, name: (c.ship || {}).name || "", why: probs[0] }); continue; }
    queue.push(c);
  }
  queue.sort((a, b) => String(a.requestedAt || "").localeCompare(String(b.requestedAt || "")));
  const batch = queue.slice(0, PUSH_BATCH);
  const nextCode = orderCodeMaker(settings, collabs);

  if (dryRun) {
    return {
      ok: true, dryRun: true, skipped,
      wouldSend: batch.length,
      more: Math.max(0, queue.length - batch.length),
      sample: batch.length ? saleOrderPayload(batch[0], nextCode(), settings, skuByCode) : null,
    };
  }

  const created = [], failed = [];
  for (const c of batch) {
    let code = "", r = null, err = "";
    /* Years of manual CSV uploads mean a number in the series may already be
       taken in Uniware. Step past it rather than make supply work out which. */
    for (let attempt = 0; attempt < 4; attempt++) {
      code = nextCode();
      r = await uniPost(sql, base, "/services/rest/v1/oms/saleOrder/create",
        saleOrderPayload(c, code, settings, skuByCode));
      err = uniErrors(r);
      if ((r.ok && r.body && r.body.successful) || !/already exist/i.test(err)) break;
    }
    if (r.ok && r.body && r.body.successful) {
      await saveCollab(sql, c.id, {
        ucCode: code, orderVia: "Unicommerce API",
        shipStatus: "Order Created", uniError: "", uniPushedAt: new Date().toISOString(),
      });
      created.push({ id: c.id, name: (c.ship || {}).name || "", code });
    } else {
      await saveCollab(sql, c.id, { uniError: err || "Unicommerce rejected the order." });
      failed.push({ id: c.id, name: (c.ship || {}).name || "", why: err });
    }
  }
  return { ok: true, created, failed, skipped, more: Math.max(0, queue.length - batch.length) };
}

/* ------------------------------------------------------------------- sync */

/* Uniware's own marketplace sync is not instant, so a row that shows no
   tracking yet is normal rather than broken. */
function readPackage(dto) {
  const pkgs = (dto && dto.shippingPackages) || [];
  if (!pkgs.length) return null;
  /* Prefer a package that actually has a tracking number on it. */
  return pkgs.find((p) => p && String(p.trackingNumber || "").trim()) || pkgs[0];
}

async function doSync(sql, base) {
  const { collabs } = await loadBoard(sql);
  const open = collabs
    .filter((c) => String(c.ucCode || "").trim())
    .filter((c) => c.shipStatus === "Order Created" || c.shipStatus === "Dispatched")
    .sort((a, b) => String(b.requestedAt || "").localeCompare(String(a.requestedAt || "")))
    .slice(0, SYNC_BATCH);

  const updated = [], unchanged = [], failed = [];
  const facility = process.env.UNI_FACILITY || "";

  for (const c of open) {
    const r = await uniPost(sql, base, "/services/rest/v1/oms/saleorder/get", {
      code: c.ucCode,
      facilityCodes: facility ? [facility] : [],
      paymentDetailRequired: false,
    });
    if (!r.ok || !r.body || !r.body.successful) {
      failed.push({ id: c.id, code: c.ucCode, why: uniErrors(r) });
      continue;
    }
    const pkg = readPackage(r.body.saleOrderDTO);
    const patch = {};
    const awb = String((pkg && pkg.trackingNumber) || "").trim();
    const courier = String((pkg && pkg.shippingProvider) || "").trim();
    const dispatched = istDate(pkg && pkg.dispatched);
    const delivered = istDate(pkg && pkg.delivered);
    const link = String((pkg && pkg.trackingLink) || "").trim();

    if (awb && awb !== c.awb) patch.awb = awb;
    if (courier && courier !== c.courier) patch.courier = courier;
    if (dispatched && dispatched !== c.dispatchDate) patch.dispatchDate = dispatched;
    if (delivered && delivered !== c.deliveryDate) patch.deliveryDate = delivered;
    if (link && link !== c.trackLink) patch.trackLink = link;

    /* Only ever forwards. Supply may have already moved a row on by hand. */
    const want = delivered ? "Delivered" : dispatched ? "Dispatched" : c.shipStatus;
    if (want !== c.shipStatus && !(c.shipStatus === "Delivered" && want === "Dispatched")) {
      patch.shipStatus = want;
    }
    if (c.uniError) patch.uniError = "";

    if (Object.keys(patch).length) {
      patch.uniSyncedAt = new Date().toISOString();
      await saveCollab(sql, c.id, patch);
      updated.push({ id: c.id, code: c.ucCode, awb: patch.awb || c.awb || "", stage: patch.shipStatus || c.shipStatus });
    } else {
      unchanged.push(c.ucCode);
    }
  }

  const state = {
    at: new Date().toISOString(),
    looked: open.length, updated: updated.length, failed: failed.length,
  };
  await writeRow(sql, STATE_ROW, state);
  return { ok: true, ...state, updated, failed, waiting: unchanged.length };
}

/* ------------------------------------------------------------------- ping */

async function doPing(sql, base) {
  /* Forces a real login rather than trusting the cached token, so "connected"
     means the credentials work right now. The token itself is never returned. */
  await accessToken(sql, base, true);
  const state = await readRow(sql, STATE_ROW);
  return {
    ok: true,
    connected: true,
    tenant: base.replace(/^https?:\/\//, ""),
    facility: process.env.UNI_FACILITY || "",
    lastSync: state || null,
  };
}

/* ----------------------------------------------------------------- handler */

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  if (req.method === "OPTIONS") return res.status(204).end();

  if (!process.env.DATABASE_URL)
    return bad(res, 500, "DATABASE_URL is not set on this deployment.");

  /* Vercel's scheduler cannot type a team code, so it carries CRON_SECRET. */
  const cronSecret = process.env.CRON_SECRET || "";
  const auth = String(req.headers.authorization || "");
  const fromCron = !!cronSecret &&
    (auth === "Bearer " + cronSecret || req.headers["x-cron-key"] === cronSecret);

  const supplyCode = process.env.TEAM_CODE || "";
  const marketingCode = process.env.MARKETING_CODE || "";
  const given = req.headers["x-team-code"] || "";
  let role = "supply";
  if (!fromCron && (supplyCode || marketingCode)) {
    if (supplyCode && given === supplyCode) role = "supply";
    else if (marketingCode && given === marketingCode) role = "marketing";
    else return bad(res, 401, "Wrong team code.");
  }

  let body = req.method === "GET" ? { op: String(req.query.op || "sync") } : req.body;
  if (typeof body === "string") { try { body = JSON.parse(body); } catch { body = null; } }
  if (!body || typeof body !== "object") return bad(res, 400, "Send a JSON body.");
  const op = String(body.op || "");

  const gaps = missingConfig();
  if (gaps.length)
    return bad(res, 503, "Unicommerce is not set up on this deployment yet. Missing: " + gaps.join(", ") + ".");

  /* Creating an order is supply's step, exactly as it is on the board. */
  if ((op === "push" || op === "preview" || op === "ping") && role === "marketing")
    return bad(res, 403, "Only the supply team creates orders in Unicommerce.");

  const base = tenantBase();
  const sql = neon(process.env.DATABASE_URL);

  try {
    if (op === "ping") return res.status(200).json(await doPing(sql, base));
    if (op === "preview") return res.status(200).json(await doPush(sql, base, body.ids, { dryRun: true }));
    if (op === "push") return res.status(200).json(await doPush(sql, base, body.ids, { dryRun: false }));
    if (op === "sync") return res.status(200).json(await doSync(sql, base));
    if (op === "autorun") {
      /* What the scheduler runs: create whatever is waiting if the board is
         set to auto, then read tracking back either way. */
      const { settings } = await loadBoard(sql);
      const push = settings.uniAutoPush ? await doPush(sql, base, null, { dryRun: false }) : null;
      const sync = await doSync(sql, base);
      return res.status(200).json({ ok: true, push, sync });
    }
    return bad(res, 400, "Unknown operation.");
  } catch (e) {
    console.error("uni api failed:", e);
    return bad(res, 502, String((e && e.message) || "The Unicommerce call failed."));
  }
}
