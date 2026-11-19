import { createHash, randomBytes, randomUUID } from "node:crypto";
import { Pool } from "pg";

const allowedKinds = new Set(["web_editor", "android_editor", "agent_controller"]);
const args = process.argv.slice(2);
function option(name, fallback = "") {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : fallback;
}
const kind = option("--kind");
const label = option("--label", kind);
const workspaceSlug = option("--workspace", "default");
if (!allowedKinds.has(kind)) {
  throw new Error("--kind must be web_editor, android_editor, or agent_controller");
}
if (!process.env.DATABASE_URL) throw new Error("DATABASE_URL is required; use the intended non-production Neon branch");
if (!label || label.length > 100 || !/^[a-z0-9][a-z0-9._ -]*$/i.test(label)) {
  throw new Error("--label must be 1-100 safe characters");
}
if (!/^[a-z0-9][a-z0-9_-]{0,62}$/i.test(workspaceSlug)) {
  throw new Error("--workspace must be a safe workspace slug");
}

const token = randomBytes(32).toString("base64url");
const tokenHash = createHash("sha256").update(token).digest("hex");
const pool = new Pool({ connectionString: process.env.DATABASE_URL, max: 1 });
try {
  const result = await pool.query(
    `INSERT INTO command_center.devices
       (id, workspace_id, device_kind, label, installation_id, token_hash, expires_at, created_at)
     SELECT $1, id, $2, $3, $4, $5, now() + interval '2 hours', now()
       FROM command_center.workspaces
      WHERE slug = $6
     RETURNING id, workspace_id, device_kind, label`,
    [randomUUID(), kind, label, randomUUID(), tokenHash, workspaceSlug],
  );
  if (result.rowCount !== 1) throw new Error("Workspace not found or device could not be provisioned");
  // The raw token is shown exactly once. Store it directly in the matching GitHub Actions secret.
  process.stdout.write(JSON.stringify({ ...result.rows[0], token }, null, 2) + "\n");
} finally {
  await pool.end();
}
