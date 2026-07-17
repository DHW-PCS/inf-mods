import tempfile
import unittest
from pathlib import Path

import requests

from download import (
    download_file,
    select_github_file,
    select_modrinth_file,
)


class FakeResponse:
    def __init__(self, payload=None, content=b"", status_code=200):
        self.payload = payload
        self.content = content
        self.status_code = status_code
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload

    def iter_content(self, chunk_size):
        del chunk_size
        yield self.content

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError(f"Unexpected request: {url}")
        return self.responses.pop(0)


def github_release(name, *assets):
    return {
        "name": name,
        "assets": [
            {"name": asset, "browser_download_url": f"https://example.com/{asset}"}
            for asset in assets
        ],
    }


class DownloadTests(unittest.TestCase):
    def test_modrinth_prefers_requested_type_then_beta_and_compatible_versions(self):
        session = FakeSession(
            [
                FakeResponse([]),
                FakeResponse([]),
                FakeResponse([]),
                FakeResponse(
                    [
                        {
                            "version_type": "beta",
                            "files": [{"filename": "mod.jar", "url": "https://example.com/mod.jar"}],
                        }
                    ]
                ),
            ]
        )
        config = {
            "mcVersion": "1.21.11",
            "mcCompatibles": ["1.21.10"],
            "modLoader": "fabric",
        }

        self.assertEqual(
            select_modrinth_file({"id": "mod", "type": "modrinth"}, config, session),
            ("mod.jar", "https://example.com/mod.jar"),
        )
        self.assertEqual(len(session.calls), 4)

    def test_release_filter_selects_first_jar_without_unbound_variable(self):
        releases = [github_release("Minecraft 1.21.11", "notes.txt", "mod.jar")]
        session = FakeSession([FakeResponse(releases)])

        self.assertEqual(
            select_github_file(
                {"repo": "owner/repo", "releaseFilter": "1.21.11"},
                {"mcVersion": "1.21.11"},
                session,
            ),
            ("mod.jar", "https://example.com/mod.jar"),
        )

    def test_version_in_release_falls_back_to_original_compatible_releases(self):
        releases = [github_release("Minecraft 1.21.10", "mod.jar")]
        session = FakeSession([FakeResponse(releases)])

        self.assertEqual(
            select_github_file(
                {"repo": "owner/repo", "versionInRelease": True},
                {"mcVersion": "1.21.11", "mcCompatibles": ["1.21.10"]},
                session,
            ),
            ("mod.jar", "https://example.com/mod.jar"),
        )

    def test_version_in_filename_ignores_non_jar_assets(self):
        releases = [
            github_release(
                "Release",
                "mod-mc1.21.11.zip",
                "mod-mc1.21.11.jar",
            )
        ]
        session = FakeSession([FakeResponse(releases)])

        self.assertEqual(
            select_github_file(
                {"repo": "owner/repo", "versionInFileName": True},
                {"mcVersion": "1.21.11"},
                session,
            ),
            ("mod-mc1.21.11.jar", "https://example.com/mod-mc1.21.11.jar"),
        )

    def test_download_is_atomic_and_sanitizes_remote_filename(self):
        response = FakeResponse(content=b"jar data")
        session = FakeSession([response])

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            download_file("../mod.jar", "https://example.com/mod.jar", output_dir, session)

            self.assertEqual((output_dir / "mod.jar").read_bytes(), b"jar data")
            self.assertFalse((output_dir / ".mod.jar.part").exists())
            self.assertTrue(response.closed)

    def test_failed_download_does_not_overwrite_existing_file(self):
        response = FakeResponse(content=b"error page", status_code=503)
        session = FakeSession([response])

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "mod.jar"
            destination.write_bytes(b"existing jar")

            with self.assertRaises(requests.HTTPError):
                download_file(
                    "mod.jar",
                    "https://example.com/mod.jar",
                    temp_dir,
                    session,
                )

            self.assertEqual(destination.read_bytes(), b"existing jar")
            self.assertFalse((Path(temp_dir) / ".mod.jar.part").exists())
            self.assertTrue(response.closed)


if __name__ == "__main__":
    unittest.main()
