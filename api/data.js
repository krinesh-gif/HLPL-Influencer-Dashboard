/*
 * Reel to Doorstep — data API backed by Neon (serverless Postgres).
 *
 * The dashboard is a static page, so it must never hold the database
 * credentials. Everything goes through this function, which reads
 * DATABASE_URL from the environment and checks a shared team code first.
 *
 * Environment variables (set in Vercel → Settings → Environment Variables):
 *   DATABASE_URL   the Neon connection string
 *   TEAM_CODE      the code your two teams type once to get in
 */
import { neon } from "@neondatabase/serverless";

const COLLECTIONS = new Set(["influencers", "collabs", "skus", "config"]);
let schemaReady = false;

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

  const expected = process.env.TEAM_CODE || "";
  const given = req.headers["x-team-code"] || "";
  if (expected && given !== expected)
    return bad(res, 401, "Wrong team code.");

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
      return res.status(200).json({ ok: true, ts: new Date().toISOString(), ...out });
    }

    if (op === "put") {
      if (!data || typeof data !== "object" || Array.isArray(data))
        return bad(res, 400, "Document body must be an object.");
      const { id: _drop, ...doc } = data;
      await sql`
        INSERT INTO docs (collection, id, data, updated_at)
        VALUES (${collection}, ${id}, ${JSON.stringify(doc)}::jsonb, now())
        ON CONFLICT (collection, id)
        DO UPDATE SET data = EXCLUDED.data, updated_at = now()`;
      return res.status(200).json({ ok: true });
    }

    if (op === "del") {
      await sql`DELETE FROM docs WHERE collection = ${collection} AND id = ${id}`;
      return res.status(200).json({ ok: true });
    }

    return bad(res, 400, "Unknown operation.");
  } catch (e) {
    console.error("data api failed:", e);
    return bad(res, 500, "The database rejected that. Try again in a moment.");
  }
}
