-- Short-lived device credentials minted from GitHub Actions OIDC identity.
-- Apply only to the non-production A/B staging branch.
ALTER TABLE command_center.devices
    ADD COLUMN IF NOT EXISTS expires_at timestamptz;

CREATE INDEX IF NOT EXISTS devices_active_token_expiry_idx
    ON command_center.devices (expires_at)
    WHERE expires_at IS NOT NULL;
