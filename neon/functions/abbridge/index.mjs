import { createHash } from "node:crypto";
import { Pool } from "pg";
import { attachDatabasePool } from "@neon/functions";
import {
  S3Client, PutObjectCommand, HeadObjectCommand, GetObjectCommand,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

const MAX_COMPRESSED = 64 * 1024 * 1024;
const MAX_EXPANDED = 256 * 1024 * 1024;
const ALLOWED_KINDS = new Set([
  "context_bundle", "scene_tree", "inspector_dump", "screenshot",
  "video", "project_archive", "logs", "animation_frames", "command_result",
]);
const BUCKET = process.env.AB_ARTIFACT_BUCKET || "godot-visual-captures";
const pool = new Pool({ connectionString: process.env.DATABASE_URL, max: 4, idleTimeoutMillis: 30_000 });
attachDatabasePool(pool);

const s3 = new S3Client({
  region: process.env.AWS_REGION,
  endpoint: process.env.AWS_ENDPOINT_URL_S3,
  forcePathStyle: true,
  ...(process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY
    ? { credentials: {
        accessKeyId: process.env.AWS_ACCESS_KEY_ID,
        secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
      } }
    : {}),
});

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}
function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}
function isUuid(value) {
  return typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}
function validDigest(value) {
  return typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
}
function bearer(request) {
  const value = request.headers.get("authorization") || "";
  const match = /^Bearer ([A-Za-z0-9._~-]{32,4096})$/.exec(value);
  return match?.[1] || null;
}
async function authenticate(request) {
  const token = bearer(request);
  if (!token) return null;
  const tokenHash = sha256(token);
  const result = await pool.query(
    `SELECT id, workspace_id, device_kind
       FROM command_center.devices
      WHERE token_hash = $1 AND revoked_at IS NULL
      LIMIT 1`,
    [tokenHash],
  );
  return result.rows[0] || null;
}
async function sessionMembership(device, sessionId) {
  const result = await pool.query(
    `SELECT id
       FROM command_center.sessions
      WHERE id = $1 AND workspace_id = $2
        AND status IN ('waiting', 'connected', 'paused')
        AND expires_at > now()
        AND $3 = ANY(ARRAY[web_device_id, android_device_id, agent_device_id])`,
    [sessionId, device.workspace_id, device.id],
  );
  return result.rowCount > 0;
}
function validManifest(m) {
  return m && typeof m === "object"
    && m.protocol_version === 1
    && isUuid(m.artifact_id) && isUuid(m.session_id)
    && ALLOWED_KINDS.has(m.kind)
    && m.content_type === "application/gzip"
    && m.encoding === "gzip"
    && Number.isSafeInteger(m.size_bytes) && m.size_bytes > 0 && m.size_bytes <= MAX_COMPRESSED
    && Number.isSafeInteger(m.uncompressed_size_bytes) && m.uncompressed_size_bytes > 0 && m.uncompressed_size_bytes <= MAX_EXPANDED
    && validDigest(m.sha256) && validDigest(m.uncompressed_sha256);
}
async function bodyJson(request) {
  const length = Number(request.headers.get("content-length") || 0);
  if (length > 32 * 1024) throw new Error("request_too_large");
  const bytes = await request.arrayBuffer();
  if (bytes.byteLength > 32 * 1024) throw new Error("request_too_large");
  try {
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw new Error("invalid_json");
  }
}
async function createSession(device) {
  if (device.device_kind !== "web_editor" && device.device_kind !== "android_editor") {
    return json({ error: "device_role_cannot_create_session" }, 403);
  }
  const ownerColumn = device.device_kind === "web_editor" ? "web_device_id" : "android_device_id";
  const result = await pool.query(
    `INSERT INTO command_center.sessions
       (workspace_id, ${ownerColumn}, status, protocol_version, expires_at, last_activity_at, metadata)
     VALUES ($1, $2, 'waiting', 1, now() + interval '1 hour', now(), '{}'::jsonb)
     RETURNING id, status, expires_at`,
    [device.workspace_id, device.id],
  );
  return json({ session_id: result.rows[0].id, status: result.rows[0].status, expires_at: result.rows[0].expires_at }, 201);
}
async function joinSession(device, request) {
  if (device.device_kind !== "agent_controller" && device.device_kind !== "android_editor") {
    return json({ error: "device_role_cannot_join_session" }, 403);
  }
  const body = await bodyJson(request);
  if (!isUuid(body?.session_id)) return json({ error: "invalid_session_id" }, 400);
  const column = device.device_kind === "agent_controller" ? "agent_device_id" : "android_device_id";
  const result = await pool.query(
    `UPDATE command_center.sessions
        SET ${column} = $1, status = 'connected', last_activity_at = now(),
            expires_at = GREATEST(expires_at, now() + interval '1 hour')
      WHERE id = $2 AND workspace_id = $3 AND status IN ('waiting', 'connected')
        AND expires_at > now() AND (${column} IS NULL OR ${column} = $1)
      RETURNING id, status, expires_at`,
    [device.id, body.session_id, device.workspace_id],
  );
  if (result.rowCount !== 1) return json({ error: "session_unavailable" }, 404);
  return json({ session_id: result.rows[0].id, status: result.rows[0].status, expires_at: result.rows[0].expires_at });
}
async function sessionHeartbeat(device, request) {
  const body = await bodyJson(request);
  if (!isUuid(body?.session_id)) return json({ error: "invalid_session_id" }, 400);
  const result = await pool.query(
    `UPDATE command_center.sessions
        SET last_activity_at = now(), expires_at = GREATEST(expires_at, now() + interval '1 hour')
      WHERE id = $1 AND workspace_id = $2 AND status IN ('waiting', 'connected', 'paused')
        AND expires_at > now()
        AND $3 = ANY(ARRAY[web_device_id, android_device_id, agent_device_id])
      RETURNING id, status, expires_at`,
    [body.session_id, device.workspace_id, device.id],
  );
  if (result.rowCount !== 1) return json({ error: "session_unavailable" }, 404);
  return json({ session_id: result.rows[0].id, status: result.rows[0].status, expires_at: result.rows[0].expires_at });
}

const ALLOWED_COMMAND_ACTIONS = new Set([
  "status", "screenshot", "click_text", "fill_placeholder", "wait",
  "assert_text", "canvas_click", "canvas_drag", "canvas_scroll",
  "press_key", "type_text", "semantic_command", "run_game", "game_view",
  "game_click", "game_input", "stop",
]);
async function enqueueCommand(device, request) {
  const body = await bodyJson(request);
  const targets = new Set(["web_editor", "android_editor", "agent_controller"]);
  if (!targets.has(body?.target) || body.target === device.device_kind) {
    return json({ error: "invalid_command_target" }, 400);
  }
  if (!ALLOWED_COMMAND_ACTIONS.has(body?.action)) return json({ error: "action_not_allowed" }, 400);
  if (!isUuid(body?.session_id) || !await sessionMembership(device, body.session_id)) {
    return json({ error: "session_forbidden" }, 403);
  }
  if (!body.args || typeof body.args !== "object" || Array.isArray(body.args)) {
    return json({ error: "command_args_must_be_object" }, 400);
  }
  if (typeof body.idempotency_key !== "string" || body.idempotency_key.length < 1 || body.idempotency_key.length > 128) {
    return json({ error: "invalid_idempotency_key" }, 400);
  }
  const priority = Number.isInteger(body.priority) && body.priority >= -10 && body.priority <= 10 ? body.priority : 0;
  const ttl = Number.isInteger(body.ttl_seconds) && body.ttl_seconds >= 15 && body.ttl_seconds <= 3600 ? body.ttl_seconds : 300;
  const result = await pool.query(
    `INSERT INTO command_center.commands
       (workspace_id, session_id, origin_device_id, target, action, args,
        status, priority, idempotency_key, created_at, expires_at, attempt_count)
     VALUES ($1,$2,$3,$4,$5,$6::jsonb,'queued',$7,$8,now(),now() + ($9 * interval '1 second'),0)
     ON CONFLICT (workspace_id, idempotency_key) DO NOTHING
     RETURNING id, status, created_at`,
    [device.workspace_id, body.session_id, device.id, body.target, body.action,
      JSON.stringify(body.args), priority, body.idempotency_key, ttl],
  );
  if (result.rowCount !== 1) {
    const existing = await pool.query(
      `SELECT id, status, created_at
         FROM command_center.commands
        WHERE workspace_id = $1 AND session_id = $2
          AND origin_device_id = $3 AND idempotency_key = $4`,
      [device.workspace_id, body.session_id, device.id, body.idempotency_key],
    );
    if (existing.rowCount === 1) return json({ command: existing.rows[0] });
    return json({ error: "idempotency_key_conflict" }, 409);
  }
  return json({ command: result.rows[0] }, 201);
}
async function claimCommand(device, request) {
  const body = await bodyJson(request);
  if (!isUuid(body?.session_id) || !await sessionMembership(device, body.session_id)) {
    return json({ error: "session_forbidden" }, 403);
  }
  const result = await pool.query(
    `WITH candidate AS (
       SELECT id
         FROM command_center.commands
        WHERE workspace_id = $1 AND session_id = $2 AND target = $3
          AND (expires_at IS NULL OR expires_at > now())
          AND (status = 'queued' OR (status IN ('claimed','running') AND claim_expires_at < now()))
        ORDER BY priority DESC, created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
     )
     UPDATE command_center.commands c
        SET status = 'claimed', claimed_by_device = $4, claimed_at = now(),
            claim_expires_at = now() + interval '60 seconds',
            attempt_count = attempt_count + 1
       FROM candidate
      WHERE c.id = candidate.id
      RETURNING c.id, c.session_id, c.target, c.action, c.args,
                c.idempotency_key, c.attempt_count, c.claim_expires_at`,
    [device.workspace_id, body.session_id, device.device_kind, device.id],
  );
  return json({ command: result.rows[0] || null });
}
async function startCommand(device, request) {
  const body = await bodyJson(request);
  if (!isUuid(body?.command_id)) return json({ error: "invalid_command_id" }, 400);
  const result = await pool.query(
    `UPDATE command_center.commands
        SET status = 'running', claim_expires_at = now() + interval '60 seconds'
      WHERE id = $1 AND workspace_id = $2 AND claimed_by_device = $3
        AND status = 'claimed' AND claim_expires_at > now()
      RETURNING id, status, claim_expires_at`,
    [body.command_id, device.workspace_id, device.id],
  );
  if (result.rowCount !== 1) return json({ error: "command_lease_lost" }, 409);
  return json({ command: result.rows[0] });
}
async function renewCommandLease(device, request) {
  const body = await bodyJson(request);
  if (!isUuid(body?.command_id)) return json({ error: "invalid_command_id" }, 400);
  const result = await pool.query(
    `UPDATE command_center.commands
        SET claim_expires_at = now() + interval '60 seconds'
      WHERE id = $1 AND workspace_id = $2 AND claimed_by_device = $3
        AND status IN ('claimed','running') AND claim_expires_at > now()
      RETURNING id, claim_expires_at`,
    [body.command_id, device.workspace_id, device.id],
  );
  if (result.rowCount !== 1) return json({ error: "command_lease_lost" }, 409);
  return json({ command: result.rows[0] });
}
async function getCommandResult(device, request) {
  const body = await bodyJson(request);
  if (!isUuid(body?.command_id)) return json({ error: "invalid_command_id" }, 400);
  const result = await pool.query(
    `SELECT c.status, cr.ok, cr.result, cr.error_code, cr.error_message, cr.duration_ms
       FROM command_center.commands c
       LEFT JOIN command_center.command_results cr ON cr.command_id = c.id
      WHERE c.id = $1 AND c.workspace_id = $2 AND c.origin_device_id = $3`,
    [body.command_id, device.workspace_id, device.id],
  );
  if (result.rowCount !== 1) return json({ error: "command_not_found" }, 404);
  const row = result.rows[0];
  if (!row.ok && !row.result) return json({ ready: false, status: row.status });
  return json({
    ready: true, status: row.status, ok: row.ok, result: row.result,
    error_code: row.error_code, error_message: row.error_message,
    duration_ms: row.duration_ms,
  });
}

async function completeCommand(device, request) {
  const body = await bodyJson(request);
  if (!isUuid(body?.command_id) || typeof body.ok !== "boolean"
      || !body.result || typeof body.result !== "object" || Array.isArray(body.result)) {
    return json({ error: "invalid_command_result" }, 400);
  }
  const duration = Number.isInteger(body.duration_ms) && body.duration_ms >= 0 && body.duration_ms <= 3600000
    ? body.duration_ms : null;
  const errorCode = typeof body.error_code === "string" ? body.error_code.slice(0, 100) : null;
  const errorMessage = typeof body.error_message === "string" ? body.error_message.slice(0, 500) : null;
  const status = body.ok ? "succeeded" : "failed";
  const result = await pool.query(
    `WITH updated AS (
       UPDATE command_center.commands
          SET status = $2, finished_at = now(), claim_expires_at = NULL,
              error_code = $5, error_message = $6
        WHERE id = $1 AND workspace_id = $3 AND claimed_by_device = $4
          AND status IN ('claimed','running') AND claim_expires_at > now()
        RETURNING id
     )
     INSERT INTO command_center.command_results
       (id, command_id, ok, result, error_code, error_message, duration_ms, created_at)
     SELECT gen_random_uuid(), id, $7, $8::jsonb, $5, $6, $9, now()
       FROM updated
     RETURNING command_id`,
    [body.command_id, status, device.workspace_id, device.id, errorCode, errorMessage,
      body.ok, JSON.stringify(body.result), duration],
  );
  if (result.rowCount !== 1) return json({ error: "command_lease_lost_or_already_completed" }, 409);
  return json({ command_id: body.command_id, status });
}

async function uploadUrl(device, request) {
  const body = await bodyJson(request);
  const manifest = body?.manifest;
  if (!validManifest(manifest)) return json({ error: "invalid_manifest" }, 400);
  if (!await sessionMembership(device, manifest.session_id)) return json({ error: "session_forbidden" }, 403);

  const key = `ab-artifacts/${device.workspace_id}/${manifest.session_id}/${manifest.artifact_id}.gz`;
  const inserted = await pool.query(
    `INSERT INTO command_center.artifacts
       (id, workspace_id, session_id, owner_device_id, kind, object_key,
        content_type, encoding, size_bytes, uncompressed_size_bytes,
        sha256, uncompressed_sha256, status, expires_at)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'pending',now() + interval '15 minutes')
     ON CONFLICT (id) DO NOTHING
     RETURNING id`,
    [manifest.artifact_id, device.workspace_id, manifest.session_id, device.id,
      manifest.kind, key, manifest.content_type, manifest.encoding,
      manifest.size_bytes, manifest.uncompressed_size_bytes, manifest.sha256,
      manifest.uncompressed_sha256],
  );
  if (inserted.rowCount !== 1) return json({ error: "artifact_id_conflict" }, 409);

  const upload_url = await getSignedUrl(
    s3,
    new PutObjectCommand({ Bucket: BUCKET, Key: key, ContentType: manifest.content_type }),
    { expiresIn: 300 },
  );
  return json({ artifact_id: manifest.artifact_id, upload_url }, 201);
}
async function finalize(device, request) {
  const body = await bodyJson(request);
  if (!isUuid(body?.artifact_id) || !validDigest(body?.sha256)) return json({ error: "invalid_finalize_request" }, 400);
  const result = await pool.query(
    `SELECT id, object_key, size_bytes, content_type, sha256
       FROM command_center.artifacts
      WHERE id = $1 AND workspace_id = $2 AND owner_device_id = $3
        AND status = 'pending' AND expires_at > now()`,
    [body.artifact_id, device.workspace_id, device.id],
  );
  const artifact = result.rows[0];
  if (!artifact) return json({ error: "artifact_not_found_or_expired" }, 404);
  if (artifact.sha256 !== body.sha256) return json({ error: "digest_mismatch" }, 409);

  let head;
  try {
    head = await s3.send(new HeadObjectCommand({ Bucket: BUCKET, Key: artifact.object_key }));
  } catch {
    return json({ error: "uploaded_object_not_found" }, 409);
  }
  if (Number(head.ContentLength) !== Number(artifact.size_bytes) || head.ContentType !== artifact.content_type) {
    await pool.query(
      "UPDATE command_center.artifacts SET status = 'rejected' WHERE id = $1 AND status = 'pending'",
      [body.artifact_id],
    );
    return json({ error: "uploaded_object_metadata_mismatch" }, 409);
  }
  const updated = await pool.query(
    `UPDATE command_center.artifacts
        SET status = 'ready', finalized_at = now()
      WHERE id = $1 AND owner_device_id = $2 AND status = 'pending'
      RETURNING id`,
    [body.artifact_id, device.id],
  );
  if (updated.rowCount !== 1) return json({ error: "finalize_race" }, 409);
  return json({ artifact_id: body.artifact_id, status: "ready" });
}
async function downloadUrl(device, request) {
  const body = await bodyJson(request);
  if (!isUuid(body?.artifact_id)) return json({ error: "invalid_artifact_id" }, 400);
  const result = await pool.query(
    `SELECT a.id, a.session_id, a.kind, a.content_type, a.encoding,
            a.size_bytes, a.uncompressed_size_bytes, a.sha256,
            a.uncompressed_sha256, a.object_key
       FROM command_center.artifacts a
      WHERE a.id = $1 AND a.workspace_id = $2 AND a.status = 'ready'
        AND a.expires_at > now()`,
    [body.artifact_id, device.workspace_id],
  );
  const artifact = result.rows[0];
  if (!artifact || !await sessionMembership(device, artifact.session_id)) {
    return json({ error: "artifact_not_found" }, 404);
  }
  const download_url = await getSignedUrl(
    s3,
    new GetObjectCommand({ Bucket: BUCKET, Key: artifact.object_key }),
    { expiresIn: 300 },
  );
  return json({
    artifact_id: artifact.id,
    download_url,
    manifest: {
      protocol_version: 1,
      artifact_id: artifact.id,
      session_id: artifact.session_id,
      kind: artifact.kind,
      content_type: artifact.content_type,
      encoding: artifact.encoding,
      size_bytes: Number(artifact.size_bytes),
      uncompressed_size_bytes: Number(artifact.uncompressed_size_bytes),
      sha256: artifact.sha256,
      uncompressed_sha256: artifact.uncompressed_sha256,
    },
  });
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") return json({ ok: true, service: "ab-artifact-control" });
    if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405);
    const device = await authenticate(request);
    if (!device) return json({ error: "unauthorized" }, 401);
    try {
      if (url.pathname === "/v1/sessions" && request.method === "POST") return await createSession(device);
      if (url.pathname === "/v1/sessions/join" && request.method === "POST") return await joinSession(device, request);
      if (url.pathname === "/v1/sessions/heartbeat" && request.method === "POST") return await sessionHeartbeat(device, request);
      if (url.pathname === "/v1/commands/enqueue") return await enqueueCommand(device, request);
      if (url.pathname === "/v1/commands/claim") return await claimCommand(device, request);
      if (url.pathname === "/v1/commands/start") return await startCommand(device, request);
      if (url.pathname === "/v1/commands/lease") return await renewCommandLease(device, request);
      if (url.pathname === "/v1/commands/result") return await getCommandResult(device, request);
      if (url.pathname === "/v1/commands/complete") return await completeCommand(device, request);
      if (url.pathname === "/v1/artifacts/upload-url") return await uploadUrl(device, request);
      if (url.pathname === "/v1/artifacts/finalize") return await finalize(device, request);
      if (url.pathname === "/v1/artifacts/download-url") return await downloadUrl(device, request);
      return json({ error: "not_found" }, 404);
    } catch (error) {
      if (error?.message === "request_too_large") return json({ error: "request_too_large" }, 413);
      if (error?.message === "invalid_json") return json({ error: "invalid_json" }, 400);
      console.error("[abbridge] request failed", error?.name || "Error");
      return json({ error: "internal_error" }, 500);
    }
  },
};
