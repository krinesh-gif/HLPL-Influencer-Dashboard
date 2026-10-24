/*
 * Reel to Doorstep — data API backed by Neon (serverless Postgres).
 *
 * The dashboard is a static page, so it must never hold the database
 * credentials. Everything goes through this function, which reads
 * DATABASE_URL from the environment and checks a shared team code first.
 *
 * Environment variables (set in Vercel → Settings → Environment Variables):
 *   DATABASE_URL     the Neon connection string
 *   TEAM_CODE        supply's code — may create orders in UC/Selloship/Shipway
 *   MARKETING_CODE   optional. Whoever enters this may add and edit shipments
 *                    but cannot push them past "Ready to Ship", and cannot
 *                    touch order codes or tracking. Leave it unset and
 *                    everyone who gets in has supply's rights.
 */
import { neon } from "@neondatabase/serverless";

const COLLECTIONS = new Set(["influencers", "collabs", "skus", "config"]);
let schemaReady = false;

/* What marketing may set a shipment to. Anything further along is supply's. */
const MARKETING_STAGES = new Set(["Draft", "Ready to Ship", "On Hold", "Cancelled"]);
/* Fields only supply writes — a marketing save keeps whatever is already stored. */
const SUPPLY_ONLY = ["ucCode", "orderVia", "courier", "awb", "dispatchDate", "deliveryDate"];

async function ensureSchema(sql) {
  if (schemaReady) return;
  await sql`
    CREATE TABLE IF NOT EXISTS docs (
      collection  text        NOT NULL,
      id          text        NOT NULL,
      data        jsonb       NOT NULL,
      updated_at  timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (collection, id)
    )`;
  await sql`CREATE INDEX IF NOT EXISTS docs_updated_at_idx ON docs (updated_at DESC)`;
  schemaReady = true;
}

const bad = (res, code, error) => res.status(code).json({ error });

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");

  if (req.method === "OPTIONS") return res.status(204).end();
  if (req.method !== "POST") return bad(res, 405, "Use POST.");

  if (!process.env.DATABASE_URL)
    return bad(res, 500, "DATABASE_URL is not set on this deployment.");

  const supplyCode = process.env.TEAM_CODE || "";
  const marketingCode = process.env.MARKETING_CODE || "";
  const given = req.headers["x-team-code"] || "";
  let role = "supply";
  if (supplyCode || marketingCode) {
    if (supplyCode && given === supplyCode) role = "supply";
    else if (marketingCode && given === marketingCode) role = "marketing";
    else return bad(res, 401, "Wrong team code.");
  }

  let body = req.body;
  if (typeof body === "string") { try { body = JSON.parse(body); } catch { body = null; } }
  if (!body || typeof body !== "object") return bad(res, 400, "Send a JSON body.");

  const { op, collection, id, data } = body;
  if (op !== "snapshot" && !COLLECTIONS.has(collection))
    return bad(res, 400, "Unknown collection.");
  if ((op === "put" || op === "del") && (typeof id !== "string" || !id))
    return bad(res, 400, "A document id is required.");

  const sql = neon(process.env.DATABASE_URL);

  try {
    await ensureSchema(sql);

    if (op === "snapshot") {
      const rows = await sql`SELECT collection, id, data FROM docs`;
      const out = { influencers: {}, collabs: {}, skus: {}, config: {} };
      for (const r of rows) {
        if (out[r.collection]) out[r.collection][r.id] = { id: r.id, ...r.data };
      }
      return res.status(200).json({ ok: true, role, ts: new Date().toISOString(), ...out });
    }

    if (op === "put") {
      if (!data || typeof data !== "object" || Array.isArray(data))
        return bad(res, 400, "Document body must be an object.");
      let { id: _drop, ...doc } = data;

      /* Marketing may raise and edit a shipment, not advance it. The clamp is
         here rather than in the page so it holds whatever the caller sends. */
      if (role === "marketing" && collection === "collabs") {
        const prev = await sql`SELECT data FROM docs WHERE collection = ${collection} AND id = ${id}`;
        const old = prev.length ? prev[0].data : null;
        if (old && !MARKETING_STAGES.has(old.shipStatus)) {
          return bad(res, 403, "That order has already gone to the courier. Ask supply to change it.");
        }
        if (doc.shipStatus && !MARKETING_STAGES.has(doc.shipStatus)) {
          return bad(res, 403, "Only the supply team marks an order created or dispatched.");
        }
        for (const f of SUPPLY_ONLY) {
          if (old && old[f] !== undefined) doc[f] = old[f];
          else delete doc[f];
        }
      }
      if (role === "marketing" && collection === "config") {
        return bad(res, 403, "Only the supply team changes the settings.");
      }
      await sql`
        INSERT INTO docs (collection, id, data, updated_at)
        VALUES (${collection}, ${id}, ${JSON.stringify(doc)}::jsonb, now())
        ON CONFLICT (collection, id)
        DO UPDATE SET data = EXCLUDED.data, updated_at = now()`;
      return res.status(200).json({ ok: true });
    }

    if (op === "del") {
      if (role === "marketing" && collection !== "collabs") {
        return bad(res, 403, "Only the supply team removes that.");
      }
      await sql`DELETE FROM docs WHERE collection = ${collection} AND id = ${id}`;
      return res.status(200).json({ ok: true });
    }

    return bad(res, 400, "Unknown operation.");
  } catch (e) {
    console.error("data api failed:", e);
    return bad(res, 500, "The database rejected that. Try again in a moment.");
  }
}
