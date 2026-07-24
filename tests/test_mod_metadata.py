import unittest

import requests

from mod_metadata import (
    extract_github_versions,
    fetch_json,
    get_github_releases,
    get_modrinth_project_versions,
    get_modrinth_projects,
    get_release_game_versions,
    latest_modrinth_versions,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload

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


class ModMetadataTests(unittest.TestCase):
    def test_fetch_json_closes_successful_and_missing_responses(self):
        successful = FakeResponse({"ok": True})
        missing = FakeResponse({}, 404)
        session = FakeSession([successful, missing])

        self.assertEqual(
            fetch_json(session, "https://example.com/data", timeout=7),
            {"ok": True},
        )
        self.assertIsNone(
            fetch_json(
                session,
                "https://example.com/missing",
                allow_not_found=True,
            )
        )

        self.assertTrue(successful.closed)
        self.assertTrue(missing.closed)
        self.assertEqual(session.calls[0][1]["timeout"], 7)

    def test_modrinth_requests_use_expected_endpoints_and_parameters(self):
        projects_response = FakeResponse(
            [{"id": "project-id", "slug": "project-slug"}]
        )
        versions_response = FakeResponse([])
        session = FakeSession([projects_response, versions_response])

        projects = get_modrinth_projects(session, ["project-slug"])
        versions = get_modrinth_project_versions(
            session,
            "project-slug",
            "fabric",
            "1.21.11",
            timeout=30,
        )

        self.assertIs(projects["project-id"], projects["project-slug"])
        self.assertEqual(versions, [])
        self.assertEqual(
            session.calls[0],
            (
                "https://api.modrinth.com/v2/projects",
                {
                    "params": {"ids": '["project-slug"]'},
                    "headers": None,
                    "timeout": 20,
                },
            ),
        )
        self.assertEqual(
            session.calls[1],
            (
                "https://api.modrinth.com/v2/project/project-slug/version",
                {
                    "params": {
                        "loaders": '["fabric"]',
                        "game_versions": '["1.21.11"]',
                    },
                    "headers": None,
                    "timeout": 30,
                },
            ),
        )

    def test_github_releases_add_token_headers_and_support_404(self):
        releases_response = FakeResponse([{"assets": []}])
        missing_response = FakeResponse({}, 404)
        session = FakeSession([releases_response, missing_response])

        releases = get_github_releases(
            session,
            "owner/repo",
            "secret",
            per_page=30,
        )
        missing = get_github_releases(
            session,
            "owner/missing",
            allow_not_found=True,
        )

        self.assertEqual(releases, [{"assets": []}])
        self.assertIsNone(missing)
        first_call = session.calls[0]
        self.assertEqual(
            first_call[0],
            "https://api.github.com/repos/owner/repo/releases",
        )
        self.assertEqual(first_call[1]["params"], {"per_page": 30})
        self.assertEqual(
            first_call[1]["headers"],
            {
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer secret",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def test_release_versions_are_filtered_and_sorted(self):
        session = FakeSession(
            [
                FakeResponse(
                    [
                        {
                            "version": "1.21.10",
                            "version_type": "release",
                            "date": "2025-10-01T00:00:00Z",
                        },
                        {
                            "version": "1.21.11",
                            "version_type": "release",
                            "date": "2025-12-01T00:00:00Z",
                        },
                        {
                            "version": "25w01a",
                            "version_type": "snapshot",
                            "date": "2026-01-01T00:00:00Z",
                        },
                    ]
                )
            ]
        )

        release_order = get_release_game_versions(session)

        self.assertEqual(release_order, ["1.21.11", "1.21.10"])
        self.assertEqual(
            latest_modrinth_versions(
                {"game_versions": ["1.21.10", "1.21.11"]},
                release_order,
            ),
            ["1.21.11", "1.21.10"],
        )

    def test_github_versions_are_filtered_deduplicated_and_sorted(self):
        releases = [
            {
                "assets": [
                    {"name": "mod-mc1.21.9.jar"},
                    {"name": "mod-mc1.21.11.jar"},
                    {"name": "duplicate-mc1.21.11.jar"},
                    {"name": "mod-mc26.1.1-fabric.jar"},
                    {"name": "ignored-mc99.0.zip"},
                    {"name": "sources.jar"},
                ]
            }
        ]

        self.assertEqual(
            extract_github_versions(releases),
            ["26.1.1", "1.21.11", "1.21.9"],
        )


if __name__ == "__main__":
    unittest.main()
