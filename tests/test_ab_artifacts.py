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


    def test_large_context_bundle_round_trip(self):
        from scripts.bridge.artifacts import MAX_UNCOMPRESSED_BYTES
        payload = {
            "scene_tree": [{"path": "Root/Node" + str(i), "properties": {"text": "context" * 80}}
                           for i in range(2500)],
            "selected_scripts": ["extends Node2D\n" + "var value = 1\n" * 100 for _ in range(20)],
        }
        data, manifest = pack_json_artifact(payload, session_id="session-large")
        self.assertLessEqual(len(data), 64 * 1024 * 1024)
        self.assertLessEqual(manifest["uncompressed_size_bytes"], MAX_UNCOMPRESSED_BYTES)
        self.assertEqual(unpack_json_artifact(data, manifest), payload)

    def test_manifest_rejects_boolean_size_and_invalid_digest(self):
        data, manifest = pack_json_artifact({"safe": True}, session_id="session-abc")
        with self.assertRaisesRegex(ArtifactError, "compressed size"):
            unpack_json_artifact(data, dict(manifest, size_bytes=True))
        with self.assertRaisesRegex(ArtifactError, "SHA-256"):
            unpack_json_artifact(data, dict(manifest, sha256="not-a-digest"))


    def test_session_lifecycle_helpers_validate_server_identity(self):
        from scripts.bridge.artifacts import (
            create_transport_session, join_transport_session, heartbeat_transport_session,
        )
        session_id = "d8a1c31f-7f3b-4d0e-9a11-8a8e5d8f1c21"
        with mock.patch("scripts.bridge.artifacts._control_request", side_effect=[
            {"session_id": session_id, "status": "waiting"},
            {"session_id": session_id, "status": "connected"},
            {"session_id": session_id, "status": "connected"},
        ]) as control:
            self.assertEqual(create_transport_session("https://api.example", "token")["session_id"], session_id)
            self.assertEqual(join_transport_session("https://api.example", "token", session_id)["status"], "connected")
            self.assertEqual(heartbeat_transport_session("https://api.example", "token", session_id)["status"], "connected")
        self.assertEqual(control.call_count, 3)

    def test_session_helpers_reject_cross_session_response(self):
        from scripts.bridge.artifacts import join_transport_session
        session_id = "d8a1c31f-7f3b-4d0e-9a11-8a8e5d8f1c21"
        other_id = "a8a1c31f-7f3b-4d0e-9a11-8a8e5d8f1c21"
        with mock.patch("scripts.bridge.artifacts._control_request", return_value={"session_id": other_id}):
            with self.assertRaisesRegex(ArtifactError, "different session"):
                join_transport_session("https://api.example", "token", session_id)


if __name__ == "__main__":
    unittest.main()
