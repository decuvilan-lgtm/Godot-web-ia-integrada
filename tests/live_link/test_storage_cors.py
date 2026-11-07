"""Tests for the explicit Neon Object Storage CORS setup helper."""
import unittest
from unittest.mock import Mock

from relay.storage_cors import (
    BUCKET,
    configure_bucket_cors,
    cors_configuration,
    validate_origin,
)


class StorageCorsTests(unittest.TestCase):
    def test_accepts_only_an_exact_https_origin(self):
        self.assertEqual(
            validate_origin("https://godot-web-ia-integrada-rt2l.onrender.com"),
            "https://godot-web-ia-integrada-rt2l.onrender.com",
        )
        for value in (
            "http://godot.example",
            "https://godot.example/path",
            "https://user:pass@godot.example",
            "https://godot.example?x=1",
            "https://*.onrender.com",
            " https://godot.example",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_origin(value)

    def test_cors_rule_is_origin_scoped_and_minimal(self):
        config = cors_configuration("https://godot-web-ia-integrada-rt2l.onrender.com")
        rule = config["CORSRules"][0]
        self.assertEqual(rule["AllowedOrigins"], ["https://godot-web-ia-integrada-rt2l.onrender.com"])
        self.assertEqual(set(rule["AllowedMethods"]), {"PUT", "GET", "HEAD"})
        self.assertEqual(rule["AllowedHeaders"], ["Content-Type"])
        self.assertEqual(rule["MaxAgeSeconds"], 300)

    def test_configure_puts_and_verifies_bucket_rule(self):
        origin = "https://godot-web-ia-integrada-rt2l.onrender.com"
        config = cors_configuration(origin)
        client = Mock()
        client.get_bucket_cors.return_value = config
        result = configure_bucket_cors(client, BUCKET, origin)
        client.put_bucket_cors.assert_called_once_with(
            Bucket=BUCKET,
            CORSConfiguration=config,
        )
        client.get_bucket_cors.assert_called_once_with(Bucket=BUCKET)
        self.assertEqual(result, config)

    def test_configure_fails_if_provider_does_not_apply_rule(self):
        client = Mock()
        client.get_bucket_cors.return_value = {"CORSRules": []}
        with self.assertRaises(RuntimeError):
            configure_bucket_cors(
                client,
                BUCKET,
                "https://godot-web-ia-integrada-rt2l.onrender.com",
            )


if __name__ == "__main__":
    unittest.main()
