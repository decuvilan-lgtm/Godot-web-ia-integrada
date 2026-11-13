import io
import unittest
import zipfile
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app import app
from github_archives import archive_url, validate_branch, validate_project_path


def make_zip(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return output.getvalue()


class FakeMetadata:
    status_code = 200

    def __init__(self, default_branch="trunk"):
        self.default_branch = default_branch

    def json(self):
        return {"private": False, "default_branch": self.default_branch}


class FakeUpstream:
    def __init__(self, url, status_code=200, body=None, size=None):
        self.status_code = status_code
        self.url = httpx.URL(url)
        self.body = body if body is not None else make_zip({
            "game-main/project.godot": b'config/name="Example"',
            "game-main/README.md": b"root project",
            "game-main/engine/native_android": bytes((0x7F,)) + b"ELF" + b"\x00" * 32,
            "game-main/examples/demo/project.godot": b'config/name="Nested"',
            "game-main/examples/demo/assets/icon.svg": b"<svg/>",
            "game-main/examples/demo/engine/native_android": bytes((0x7F,)) + b"ELF" + b"\x00" * 32,
        })
        self.headers = {"content-length": str(size if size is not None else len(self.body))}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_bytes(self, chunk_size):
        yield self.body


class FakeClient:
    status_code = 200
    default_branch = "trunk"
    declared_size = None

    def __init__(self, *args, **kwargs):
        self.metadata = FakeMetadata(self.default_branch)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url):
        response = FakeMetadata(self.default_branch)
        response.status_code = self.status_code
        return response

    def stream(self, method, url):
        branch = url.split("/refs/heads/", 1)[-1]
        root = "game-" + branch.replace("/", "-")
        entries = {
            f"{root}/project.godot": b'config/name="Example"',
            f"{root}/README.md": b"root project",
            f"{root}/engine/native_android": bytes((0x7F,)) + b"ELF" + b"\x00" * 32,
            f"{root}/examples/demo/project.godot": b'config/name="Nested"',
            f"{root}/examples/demo/assets/icon.svg": b"<svg/>",
            f"{root}/examples/demo/engine/native_android": bytes((0x7F,)) + b"ELF" + b"\x00" * 32,
        }
        body = make_zip(entries)
        return FakeUpstream(
            url,
            status_code=self.status_code,
            body=body,
            size=self.declared_size,
        )


class GitHubArchiveTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_archive_url_supports_named_and_slash_branches(self):
        self.assertEqual(
            archive_url("octocat", "hello-world", "release/2.0"),
            "https://codeload.github.com/octocat/hello-world/zip/refs/heads/release/2.0",
        )

    def test_invalid_branch_and_project_paths_are_rejected(self):
        for branch in ("../main", "/main", "main//next", "main\\evil", "main?x=1"):
            with self.subTest(branch=branch):
                with self.assertRaises(Exception):
                    validate_branch(branch)
        for path in ("../outside", "/absolute", "src//game", "src/./game", "src\\game"):
            with self.subTest(path=path):
                with self.assertRaises(Exception):
                    validate_project_path(path)

    def test_default_branch_is_resolved_from_public_repository_metadata(self):
        with patch("github_archives.httpx.AsyncClient", FakeClient):
            response = self.client.get("/v1/github/example/game/archive")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-github-ref"], "trunk")
        self.assertTrue(response.headers["content-disposition"].endswith('example-game-trunk.zip"'))

    def test_public_root_project_archive_is_streamed(self):
        with patch("github_archives.httpx.AsyncClient", FakeClient):
            response = self.client.get(
                "/v1/github/example/game/archive?branch=main",
                headers={"Origin": "https://godot-web-ia-integrada-rt2l.onrender.com"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-github-ref"], "main")
        self.assertIn("x-github-ref", response.headers.get("access-control-expose-headers", "").lower())
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertIn("game-main/project.godot", archive.namelist())
            self.assertIn("game-main/README.md", archive.namelist())
            self.assertNotIn("game-main/engine/native_android", archive.namelist())
        self.assertEqual(response.headers["x-godot-web-excluded-count"], "1")
        self.assertEqual(response.headers["x-godot-web-excluded-files"], "engine/native_android")

    def test_nested_project_is_repacked_with_project_file_at_zip_root(self):
        with patch("github_archives.httpx.AsyncClient", FakeClient):
            response = self.client.get("/v1/github/example/game/archive?branch=release%2F2.0&path=examples%2Fdemo")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-github-ref"], "release/2.0")
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = set(archive.namelist())
            self.assertIn("project.godot", names)
            self.assertIn("assets/icon.svg", names)
            self.assertNotIn("README.md", names)
            self.assertNotIn("engine/native_android", names)
            self.assertEqual(archive.read("project.godot"), b'config/name="Nested"')
        self.assertEqual(response.headers["x-godot-web-excluded-count"], "1")

    def test_missing_public_repository_is_reported_as_not_found(self):
        class MissingClient(FakeClient):
            status_code = 404
        with patch("github_archives.httpx.AsyncClient", MissingClient):
            response = self.client.get("/v1/github/example/missing/archive?branch=main")
        self.assertEqual(response.status_code, 404)

    def test_source_archive_over_128_mib_is_accepted_when_filtered_output_is_small(self):
        class LargeButAllowedClient(FakeClient):
            declared_size = 128 * 1024 * 1024 + 1
        with patch("github_archives.httpx.AsyncClient", LargeButAllowedClient):
            response = self.client.get("/v1/github/example/large/archive?branch=main&path=examples%2Fdemo")
        self.assertEqual(response.status_code, 200)
        self.assertLess(len(response.content), 128 * 1024 * 1024)

    def test_declared_source_archive_over_256_mib_is_rejected_before_download(self):
        class TooLargeClient(FakeClient):
            declared_size = 256 * 1024 * 1024 + 1
        with patch("github_archives.httpx.AsyncClient", TooLargeClient):
            response = self.client.get("/v1/github/example/large/archive?branch=main")
        self.assertEqual(response.status_code, 413)

    def test_nested_project_must_contain_project_godot(self):
        class MissingProjectClient(FakeClient):
            def stream(self, method, url):
                branch = url.split("/refs/heads/", 1)[-1]
                root = "game-" + branch.replace("/", "-")
                body = make_zip({f"{root}/examples/demo/README.md": b"not a project"})
                return FakeUpstream(url, body=body)
        with patch("github_archives.httpx.AsyncClient", MissingProjectClient):
            response = self.client.get("/v1/github/example/game/archive?branch=main&path=examples%2Fdemo")
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
