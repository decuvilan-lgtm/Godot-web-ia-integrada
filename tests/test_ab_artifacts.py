import unittest
from unittest import mock

from scripts.bridge.artifacts import (
    ArtifactError, download_artifact, pack_json_artifact,
    unpack_json_artifact, upload_artifact,
)


class ArtifactTests(unittest.TestCase):
    def test_json_round_trip_and_deterministic_compression(self):
        payload = {"scene": "Escena ñ", "nodes": [{"name": "Player", "x": 12}]}
        first, manifest = pack_json_artifact(payload, session_id="session-abc")
        second, _ = pack_json_artifact(payload, session_id="session-abc", artifact_id=manifest["artifact_id"])
        self.assertEqual(first, second)
        self.assertEqual(payload, unpack_json_artifact(first, manifest))
        self.assertEqual(len(first), manifest["size_bytes"])

    def test_rejects_corrupted_bytes(self):
        data, manifest = pack_json_artifact({"large": "context"}, session_id="session-abc")
        with self.assertRaisesRegex(ArtifactError, "SHA-256"):
            unpack_json_artifact(data + b"x", manifest)

    def test_rejects_invalid_kind_and_url(self):
        with self.assertRaises(ArtifactError):
            pack_json_artifact({}, session_id="session-abc", kind="unknown")
        with self.assertRaises(ArtifactError):
            upload_artifact("http://example.com/signed", b"data")
        with self.assertRaises(ArtifactError):
            download_artifact("https://user:pass@example.com/signed", {})

    def test_download_verifies_hash(self):
        data, manifest = pack_json_artifact({"ok": True}, session_id="session-abc")
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = data
        opener = mock.MagicMock()
        opener.open.return_value = response
        with mock.patch("scripts.bridge.artifacts.urllib.request.build_opener", return_value=opener):
            self.assertEqual(data, download_artifact("https://storage.example/signed", manifest))
            broken = dict(manifest, sha256="0" * 64)
            with self.assertRaisesRegex(ArtifactError, "SHA-256"):
                download_artifact("https://storage.example/signed", broken)

    def test_upload_uses_put_and_does_not_follow_redirects(self):
        response = mock.MagicMock()
        response.__enter__.return_value.status = 204
        opener = mock.MagicMock()
        opener.open.return_value = response
        with mock.patch("scripts.bridge.artifacts.urllib.request.build_opener", return_value=opener):
            upload_artifact("https://storage.example/signed", b"payload")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(request.data, b"payload")


if __name__ == "__main__":
    unittest.main()
