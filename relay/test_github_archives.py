import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app import app
from github_archives import archive_url


class FakeUpstream:
    def __init__(self, status_code=200, body=b"PK" + bytes((3, 4)) + b"fake-zip", size=None):
        self.status_code = status_code
        self.url = httpx.URL("https://codeload.github.com/example/game/zip/refs/heads/main")
        self.headers = {"content-length": str(size if size is not None else len(body))}
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_bytes(self, chunk_size):
        yield self.body


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.response = FakeUpstream()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method, url):
        return self.response


class GitHubArchiveTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_archive_url_is_fixed_to_public_main_branch(self):
        self.assertEqual(
            archive_url("octocat", "hello-world"),
            "https://codeload.github.com/octocat/hello-world/zip/refs/heads/main",
        )

    def test_invalid_owner_or_repository_is_rejected(self):
        response = self.client.get("/v1/github/../repo/archive")
        self.assertIn(response.status_code, {404, 422})
        response = self.client.get("/v1/github/owner/repo%2Fother/archive")
        self.assertIn(response.status_code, {404, 422})

    def test_public_archive_is_streamed_without_credentials(self):
        with patch("github_archives.httpx.AsyncClient", FakeClient):
            response = self.client.get("/v1/github/example/game/archive")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"PK" + bytes((3, 4)) + b"fake-zip")
        self.assertEqual(response.headers["x-github-ref"], "main")
        self.assertEqual(response.headers["x-github-repository"], "example/game")
        self.assertIn("no-store", response.headers["cache-control"])

    def test_missing_public_repository_is_reported_as_not_found(self):
        class MissingClient(FakeClient):
            def __init__(self, *args, **kwargs):
                self.response = FakeUpstream(status_code=404)
        with patch("github_archives.httpx.AsyncClient", MissingClient):
            response = self.client.get("/v1/github/example/private-repo/archive")
        self.assertEqual(response.status_code, 404)

    def test_declared_oversized_archive_is_rejected_before_download(self):
        class LargeClient(FakeClient):
            def __init__(self, *args, **kwargs):
                self.response = FakeUpstream(size=128 * 1024 * 1024 + 1)
        with patch("github_archives.httpx.AsyncClient", LargeClient):
            response = self.client.get("/v1/github/example/large/archive")
        self.assertEqual(response.status_code, 413)


if __name__ == "__main__":
    unittest.main()
