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
            unpack_json_artifact(data[:-1] + bytes([data[-1] ^ 1]), manifest)

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


    def test_upload_flow_requires_server_finalization(self):
        data, manifest = pack_json_artifact({"scene": "Main"}, session_id="session-abc")
        responses = [
            {"artifact_id": manifest["artifact_id"], "upload_url": "https://storage.example/put"},
            {"artifact_id": manifest["artifact_id"], "status": "ready"},
        ]
        with (
            mock.patch("scripts.bridge.artifacts.pack_json_artifact", return_value=(data, manifest)),
            mock.patch("scripts.bridge.artifacts._control_request", side_effect=responses) as control,
            mock.patch("scripts.bridge.artifacts.upload_artifact") as upload,
        ):
             mock.patch("scripts.bridge.artifacts.upload_artifact") as upload:
            result = __import__("scripts.bridge.artifacts", fromlist=["upload_json_artifact"]).upload_json_artifact(
                "https://api.example", "device-token", {"scene": "Main"}, session_id="session-abc"
            )
        self.assertEqual(result["artifact_id"], manifest["artifact_id"])
        self.assertEqual(control.call_count, 2)
        upload.assert_called_once()
        self.assertEqual(upload.call_args.args[0], "https://storage.example/put")

    def test_download_flow_checks_artifact_identity_and_hash(self):
        from scripts.bridge.artifacts import download_json_artifact
        data, manifest = pack_json_artifact({"scene": "Main"}, session_id="session-abc")
        with mock.patch("scripts.bridge.artifacts._control_request", return_value={
            "artifact_id": manifest["artifact_id"],
            "download_url": "https://storage.example/get",
            "manifest": manifest,
        }), mock.patch("scripts.bridge.artifacts.download_artifact", return_value=data):
            self.assertEqual(
                download_json_artifact("https://api.example", "device-token", manifest["artifact_id"]),
                {"scene": "Main"},
            )

    def test_control_plane_rejects_non_origin_base_and_bad_token(self):
        from scripts.bridge.artifacts import _control_request
        with self.assertRaises(ArtifactError):
            _control_request("https://api.example/path", "token", "/v1/artifacts/upload-url", {})
        with self.assertRaises(ArtifactError):
            _control_request("https://api.example", "bad token", "/v1/artifacts/upload-url", {})


if __name__ == "__main__":
    unittest.main()
