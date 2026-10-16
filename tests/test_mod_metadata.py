import json
import unittest

import requests

from mod_metadata import (
    ReleaseCatalogue,
    extract_github_versions,
    fetch_json,
    get_github_releases,
    get_github_versions,
    get_modrinth_projects,
    load_release_catalogue,
    manifest_release_versions,
    modrinth_supported_versions,
    release_minecraft_versions,
)


from tests.support import FakeResponse, FakeSession


SERIES = ("26.1", "26.1.1", "26.1.2", "26.2", "26.3")


def manifest_payload(versions):
    """Build a Mojang-shaped manifest, which lists the newest release first."""

    entries = [
        {
            "id": version,
            "type": "release",
            "releaseTime": f"2026-01-{position + 1:02d}T00:00:00Z",
        }
        for position, version in enumerate(versions)
    ]
    return {"versions": list(reversed(entries))}


def catalogue_of(*versions):
    return ReleaseCatalogue(manifest_release_versions(manifest_payload(versions)))


class ReleaseCatalogueTests(unittest.TestCase):
    def test_a_series_head_stands_for_its_whole_series(self):
        catalogue = catalogue_of(*SERIES)
        self.assertEqual(catalogue.support(["26.1"]), ["26.1.2", "26.1.1", "26.1"])
        self.assertEqual(catalogue.support(["26.3"]), ["26.3"])

    def test_a_patch_stands_for_itself_and_later_series_members_only(self):
        catalogue = catalogue_of(*SERIES)
        self.assertEqual(catalogue.support(["26.1.2"]), ["26.1.2"])
        self.assertEqual(catalogue.support(["26.1.1"]), ["26.1.2", "26.1.1"])

    def test_declarations_without_a_real_release_stand_for_nothing(self):
        catalogue = catalogue_of(*SERIES)
        for declaration in ["26.1.99", "26.1.2.3", "99.0", "26.9"]:
            with self.subTest(declaration=declaration):
                self.assertEqual(catalogue.support([declaration]), [])

    def test_snapshot_and_prerelease_declarations_are_discarded(self):
        catalogue = catalogue_of(*SERIES)
        declarations = ["26.3-pre-1", "26.4-snapshot-1", "26.1-rc-1", "24w14a", "26.1.2-beta"]
        self.assertEqual(catalogue.support(declarations), [])

    def test_series_expansion_does_not_reach_across_series(self):
        catalogue = catalogue_of("26.1", "26.1.1", "26.10")
        self.assertEqual(catalogue.support(["26.1"]), ["26.1.1", "26.1"])
        self.assertEqual(catalogue.support(["26.10"]), ["26.10"])

    def test_ordering_follows_the_manifest_not_the_version_numbers(self):
        # The manifest says 26.1.10 shipped before 26.1.9. Nothing may re-sort that,
        # which is also why this span counts as forward rather than reversed.
        catalogue = catalogue_of("26.1.10", "26.1.9")
        self.assertEqual(catalogue.support(["26.1.10"]), ["26.1.9", "26.1.10"])
        self.assertEqual(catalogue.span("26.1.10", "26.1.9"), {"26.1.10", "26.1.9"})

    def test_a_span_rejects_reversed_and_absent_endpoints(self):
        catalogue = catalogue_of(*SERIES)
        for start, end in [("26.3", "26.1"), ("26.1", "26.1.99")]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                catalogue.span(start, end)


class ReleaseTitleTests(unittest.TestCase):
    def test_ranges_are_exact_manifest_spans(self):
        catalogue = catalogue_of(*SERIES)
        for title, expected in [
            ("Carpet 99.0 for Minecraft 26.1.2-26.3", ["26.3", "26.2", "26.1.2"]),
            ("Minecraft 26.1.1-26.3", ["26.3", "26.2", "26.1.2", "26.1.1"]),
            ("Minecraft 26.1–26.1.2", ["26.1.2", "26.1.1", "26.1"]),
        ]:
            with self.subTest(title=title):
                self.assertEqual(release_minecraft_versions(title, catalogue), expected)

    def test_a_range_upper_bound_is_not_stretched_forward(self):
        catalogue = catalogue_of(*SERIES)
        for title, expected in [
            ("Minecraft 26.1-26.1.1", ["26.1.1", "26.1"]),
            ("Minecraft 26.1.1-26.1.2", ["26.1.2", "26.1.1"]),
        ]:
            with self.subTest(title=title):
                self.assertEqual(release_minecraft_versions(title, catalogue), expected)

    def test_bare_versions_in_a_title_take_the_series_default(self):
        catalogue = catalogue_of(*SERIES)
        for title, expected in [
            ("Carpet Mod 26.1 for Minecraft 26.1", ["26.1.2", "26.1.1", "26.1"]),
            ("Carpet Mod 26.3 for Minecraft 26.3", ["26.3"]),
            ("Carpet Mod 26.4-beta-3 for Minecraft 26.4-snapshot-4", []),
            ("Carpet for Minecraft 99.0", []),
        ]:
            with self.subTest(title=title):
                self.assertEqual(release_minecraft_versions(title, catalogue), expected)

    def test_a_wildcard_names_the_same_series_a_bare_head_does(self):
        catalogue = catalogue_of(*SERIES)
        self.assertEqual(
            release_minecraft_versions("Minecraft 26.1.x", catalogue),
            catalogue.support(["26.1"]),
        )

    def test_ranges_stop_generation_without_real_endpoints(self):
        catalogue = catalogue_of(*SERIES)
        for title in ["Minecraft 26.1-26.1.99", "Minecraft 26.1.1-26.1"]:
            with self.subTest(title=title), self.assertRaises(ValueError):
                release_minecraft_versions(title, catalogue)


class GithubVersionTests(unittest.TestCase):
    def test_release_titles_are_claimed_through_the_catalogue(self):
        releases = [
            {"name": "Carpet Mod 26.3 for Minecraft 26.3", "assets": [{"name": "carpet.jar"}]},
            {"name": "Carpet Mod 26.2 for Minecraft 26.2", "assets": [{"name": "carpet.jar"}]},
            {"name": "Carpet Mod 26.1 for Minecraft 26.1", "assets": [{"name": "carpet.jar"}]},
            {"name": "Carpet Mod 99.0 for Minecraft 99.0", "assets": []},
            {
                "name": "Carpet Mod 26.2-beta for Minecraft 26.2",
                "draft": True,
                "assets": [{"name": "carpet.jar"}],
            },
        ]
        self.assertEqual(
            extract_github_versions(releases, catalogue_of(*SERIES), version_in_release=True),
            ["26.3", "26.2", "26.1.2", "26.1.1", "26.1"],
        )

    def test_file_names_are_claimed_through_the_catalogue(self):
        releases = [
            {
                "assets": [
                    {"name": "mod-mc26.1.1.jar"},
                    {"name": "mod-mc26.3.jar"},
                    {"name": "duplicate-mc26.3.jar"},
                    {"name": "ignored-mc26.1.2.zip"},
                    {"name": "sources.jar"},
                ]
            }
        ]
        self.assertEqual(
            extract_github_versions(releases, catalogue_of(*SERIES)),
            ["26.3", "26.1.2", "26.1.1"],
        )

    def test_github_title_mode_reads_the_releases_it_is_given(self):
        releases = [{"name": "Minecraft 26.1-26.1.2", "assets": [{"name": "extra.jar"}]}]
        session = FakeSession([FakeResponse(releases)])
        self.assertEqual(
            get_github_versions(
                session, "gnembon/carpet-extra", catalogue_of(*SERIES), version_in_release=True
            ),
            ["26.1.2", "26.1.1", "26.1"],
        )


class ModrinthVersionTests(unittest.TestCase):
    def test_project_game_versions_expand_through_the_catalogue(self):
        catalogue = catalogue_of(*SERIES)
        self.assertEqual(
            modrinth_supported_versions(
                {"game_versions": ["26.3-pre-1", "26.1.2", "24w14a", "26.3"]}, catalogue
            ),
            ["26.3", "26.1.2"],
        )
        self.assertEqual(modrinth_supported_versions(None, catalogue), [])


class ManifestTests(unittest.TestCase):
    def test_releases_are_ordered_by_publication_time(self):
        payload = {
            "versions": [
                {"id": "26.2", "type": "release", "releaseTime": "2026-06-16T00:00:00Z"},
                {"id": "26.1", "type": "release", "releaseTime": "2026-03-24T00:00:00Z"},
                {"id": "26.1.1", "type": "release", "releaseTime": "2026-04-01T00:00:00Z"},
                {"id": "26.1-snapshot-1", "type": "snapshot", "releaseTime": "2026-03-01T00:00:00Z"},
            ]
        }
        self.assertEqual(manifest_release_versions(payload), ["26.1", "26.1.1", "26.2"])

    def test_ties_use_the_manifest_position_not_the_version_string(self):
        # The array holds the newer release first, so 26.1 is the later of the two even
        # though its version string sorts before 26.1.1.
        payload = {
            "versions": [
                {"id": "26.1", "type": "release", "releaseTime": "2026-01-01T00:00:00Z"},
                {"id": "26.1.1", "type": "release", "releaseTime": "2026-01-01T00:00:00Z"},
            ]
        }
        self.assertEqual(manifest_release_versions(payload), ["26.1.1", "26.1"])

    def test_invalid_mojang_manifest_is_rejected(self):
        for payload in [
            {},
            {"versions": []},
            {"versions": [None]},
            {"versions": [{"type": "release", "id": "26.1", "releaseTime": "invalid"}]},
        ]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                manifest_release_versions(payload)

    def test_a_failed_manifest_stops_the_catalogue_loading(self):
        with self.assertRaises(requests.HTTPError):
            load_release_catalogue(FakeSession([FakeResponse({}, 503)]))


class RequestTests(unittest.TestCase):
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
        projects_response = FakeResponse([{"id": "project-id", "slug": "project-slug"}])
        session = FakeSession([projects_response])

        projects = get_modrinth_projects(session, ["project-slug"])

        self.assertEqual(projects["project-id"], projects_response.payload[0])
        self.assertEqual(projects["project-slug"], projects_response.payload[0])
        url, kwargs = session.calls[0]
        self.assertEqual(url, "https://api.modrinth.com/v2/projects")
        self.assertEqual(json.loads(kwargs["params"]["ids"]), ["project-slug"])

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
        self.assertEqual(first_call[1]["headers"]["Authorization"], "Bearer secret")
        self.assertNotIn("Authorization", session.calls[1][1]["headers"])


if __name__ == "__main__":
    unittest.main()
