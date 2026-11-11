import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import github_import


class GitHubImportProxyTests(unittest.TestCase):
    def setUp(self):
        github_import._rate_events.clear()
        self.app = FastAPI()
        self.app.include_router(github_import.router)
        self.client = TestClient(self.app)

    def test_repository_names_are_restricted_to_owner_and_repo_segments(self):
        self.assertEqual(github_import._validate_repository("godotengine", "godot"), ("godotengine", "godot"))
        for owner, repo in (
            ("../attacker", "repo"),
            ("owner", "../repo"),
            ("owner", "repo?download=1"),
            ("owner", "repo/name"),
        ):
            with self.subTest(owner=owner, repo=repo):
                with self.assertRaises(Exception):
                    github_import._validate_repository(owner, repo)

    def test_proxy_returns_zip_with_safe_headers(self):
        payload = b"PK\\x03\\x04fake-zip"
        with patch("github_import._download_archive", new=AsyncMock(return_value=payload)):
            response = self.client.get("/v1/github/import/MCMLXXXV/godot-minimal-template")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, payload)
        self.assertEqual(response.headers["content-type"], "application/zip")
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-github-repository"], "MCMLXXXV/godot-minimal-template")

    def test_proxy_rejects_invalid_repository_before_network_access(self):
        with patch("github_import._download_archive", new=AsyncMock()) as download:
            response = self.client.get("/v1/github/import/owner/repo%3Fquery")
        self.assertEqual(response.status_code, 422)
        download.assert_not_awaited()

    def test_rate_limit_blocks_ninth_request_per_client_window(self):
        async def run():
            for _ in range(github_import.RATE_LIMIT):
                await github_import._check_rate_limit("test-client")
            with self.assertRaises(Exception) as raised:
                await github_import._check_rate_limit("test-client")
            self.assertEqual(getattr(raised.exception, "status_code", None), 429)
        asyncio.run(run())

    def test_download_rejects_redirects_to_untrusted_hosts(self):
        class FakeResponse:
            status_code = 302
            headers = {"location": "https://attacker.example/archive.zip"}
        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            async def get(self, url, **kwargs):
                if url.endswith("/repos/acme/game"):
                    return type("Metadata", (), {"status_code": 200, "json": lambda self: {"private": False}})()
                return FakeResponse()
        with patch("github_import.httpx.AsyncClient", FakeClient):
            with self.assertRaises(Exception) as raised:
                asyncio.run(github_import._download_archive("acme", "game"))
        self.assertEqual(getattr(raised.exception, "status_code", None), 502)


if __name__ == "__main__":
    unittest.main()
