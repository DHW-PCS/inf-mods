import unittest

import requests

from mod_metadata import (
    extract_github_versions,
    manifest_release_versions,
    release_minecraft_versions,
    fetch_json,
    get_github_releases,
    get_github_versions,
    get_modrinth_projects,
    get_release_game_versions,
    latest_modrinth_versions,
)


from tests.support import FakeResponse, FakeSession


class ModMetadataTests(unittest.TestCase):
    def test_manifest_ranges_use_real_releases_in_publication_order(self):
        payload = {
            "versions": [
                {"id": "26.1.2", "type": "release", "releaseTime": "2026-04-04T00:00:00Z"},
                {"id": "1.20.6", "type": "release", "releaseTime": "2024-04-01T00:00:00Z"},
                {"id": "26.1", "type": "release", "releaseTime": "2026-04-01T00:00:00Z"},
                {"id": "1.21.1", "type": "release", "releaseTime": "2024-08-01T00:00:00Z"},
                {"id": "26.1-snapshot-1", "type": "snapshot", "releaseTime": "2026-03-01T00:00:00Z"},
                {"id": "1.21", "type": "release", "releaseTime": "2024-06-01T00:00:00Z"},
            ]
        }
        official = manifest_release_versions(payload)
        self.assertEqual(
            release_minecraft_versions("Carpet 99.0 for Minecraft 1.20.6-1.21.1", official),
            {"1.20.6", "1.21", "1.21.1"},
        )
        self.assertEqual(release_minecraft_versions("Minecraft 26.1.x", official), {"26.1", "26.1.2"})
        self.assertEqual(
            release_minecraft_versions("Minecraft 26.1–26.1.2", official), {"26.1", "26.1.2"}
        )
        self.assertEqual(
            release_minecraft_versions("Minecraft 1.21.1-26.1", official), {"1.21.1", "26.1"}
        )
        self.assertEqual(
            release_minecraft_versions("Minecraft 1.21 and 1.21.1", official), {"1.21", "1.21.1"}
        )

    def test_range_expansion_fails_without_valid_manifest_endpoints(self):
        for title, official in [
            ("Minecraft 1.21-1.21.1", None),
            ("Minecraft 1.21.x", None),
            ("Minecraft 1.21-1.21.99", ["1.21", "1.21.1"]),
            ("Minecraft 1.21.1-1.21", ["1.21", "1.21.1"]),
        ]:
            with self.subTest(title=title, official=official), self.assertRaises(ValueError):
                release_minecraft_versions(title, official)

    def test_github_title_versions_fetch_official_manifest_and_propagate_failure(self):
        releases = [{"name": "Minecraft 1.20.6-1.21.1", "assets": [{"name": "extra.jar"}]}]
        manifest = {
            "versions": [
                {"id": v, "type": "release", "releaseTime": f"2024-06-{i:02d}T00:00:00Z"}
                for i, v in enumerate(["1.20.6", "1.21", "1.21.1"], 1)
            ]
        }
        session = FakeSession([FakeResponse(releases), FakeResponse(manifest)])
        self.assertEqual(
            get_github_versions(session, "gnembon/carpet-extra", version_in_release=True),
            ["1.21.1", "1.21", "1.20.6"],
        )
        self.assertEqual(
            session.calls[1][0], "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
        )
        with self.assertRaises(requests.HTTPError):
            get_github_versions(
                FakeSession([FakeResponse(releases), FakeResponse({}, 503)]),
                "gnembon/carpet-extra",
                version_in_release=True,
            )

    def test_invalid_mojang_manifest_is_rejected(self):
        for payload in [
            {},
            {"versions": []},
            {"versions": [None]},
            {"versions": [{"type": "release", "id": "1.21", "releaseTime": "invalid"}]},
        ]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                manifest_release_versions(payload)

    def test_carpet_release_titles_extract_ranges_without_mod_versions(self):
        releases = [
            {
                "name": "Carpet Extra 1.4.185 for Minecraft 1.21.9-1.21.11",
                "assets": [{"name": "carpet-extra-1.21.9-1.4.185.jar"}],
            },
            {"name": "Carpet for Minecraft 26.3-snapshot-9", "assets": [{"name": "carpet.jar"}]},
            {"name": "Carpet for Minecraft 99.0", "assets": []},
        ]
        self.assertEqual(
            extract_github_versions(
                releases, version_in_release=True, official_versions=["1.21.9", "1.21.10", "1.21.11"]
            ),
            ["1.21.11", "1.21.10", "1.21.9"],
        )

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
        session = FakeSession([projects_response])

        projects = get_modrinth_projects(session, ["project-slug"])

        self.assertIs(projects["project-id"], projects["project-slug"])
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
        for project, order, expected in [
            ({"game_versions": ["1.21.10", "1.21.11"]}, release_order, ["1.21.11", "1.21.10"]),
            (
                {"game_versions": ["1.21.9", "26.1.1", "1.21.11", "24w14a"]},
                ["26.2", "26.1.1", "1.21.11", "1.21.10", "1.21.9"],
                ["26.1.1", "1.21.11", "1.21.9"],
            ),
        ]:
            with self.subTest(project=project):
                self.assertEqual(latest_modrinth_versions(project, order), expected)

    def test_github_versions_are_filtered_deduplicated_and_sorted(self):
        releases = [
            {
                "assets": [
                    {"name": "mod-mc1.21.9.jar"},
                    {"name": "mod-mc1.21.11.jar"},
                    {"name": "duplicate-mc1.21.11.jar"},
                    {"name": "mod-mc26.1.1-fabric.jar"},
                    {"name": "ignored-mc99.0.zip"},
                    {"name": "tis-mc26.3-snapshot-2.jar"},
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
