"""Configure the private Neon Object Storage bucket for the deployed Godot Web origin.

Run manually from the relay environment after its scoped storage credential and
COMMAND_CENTER_STORAGE_CORS_ORIGIN have been configured. This script never prints
credentials or presigned URLs and does not run automatically at application startup.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

BUCKET = "godot-visual-captures"


def validate_origin(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("A single exact HTTPS origin is required.")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or "*" in value
    ):
        raise ValueError("Origin must be an exact HTTPS origin without path, credentials, query or wildcard.")
    return f"https://{parsed.netloc}"


def cors_configuration(origin: str) -> dict:
    exact_origin = validate_origin(origin)
    return {
        "CORSRules": [
            {
                "AllowedOrigins": [exact_origin],
                "AllowedMethods": ["PUT", "GET", "HEAD"],
                "AllowedHeaders": ["Content-Type"],
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 300,
            }
        ]
    }


def configure_bucket_cors(client, bucket: str, origin: str) -> dict:
    config = cors_configuration(origin)
    client.put_bucket_cors(Bucket=bucket, CORSConfiguration=config)
    result = client.get_bucket_cors(Bucket=bucket)
    rules = result.get("CORSRules", [])
    if not any(
        rule.get("AllowedOrigins") == config["CORSRules"][0]["AllowedOrigins"]
        and set(rule.get("AllowedMethods", [])) >= {"PUT", "GET", "HEAD"}
        and set(rule.get("AllowedHeaders", [])) >= {"Content-Type"}
        for rule in rules
    ):
        raise RuntimeError("Neon Object Storage did not return the expected CORS rule.")
    return config


def main() -> None:
    try:
        import boto3
    except ImportError as exc:
        raise SystemExit("Install relay/requirements.txt before configuring storage CORS.") from exc

    endpoint = os.environ.get("AWS_ENDPOINT_URL_S3", "").strip()
    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
    region = os.environ.get("AWS_REGION", "").strip()
    origin = os.environ.get("COMMAND_CENTER_STORAGE_CORS_ORIGIN", "")

    if not all((endpoint, access_key, secret_key, region)):
        raise SystemExit("Missing AWS_ENDPOINT_URL_S3, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY or AWS_REGION.")
    validate_origin(origin)

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    configure_bucket_cors(client, BUCKET, origin)
    print(f"CORS configured and verified for {validate_origin(origin)} on private bucket {BUCKET}.")


if __name__ == "__main__":
    main()
