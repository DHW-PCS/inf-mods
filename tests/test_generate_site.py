import tempfile
import unittest

import yaml
from datetime import datetime, timezone
from pathlib import Path

from generate_site import (
    ModEntry,
    VersionReadiness,
    collect_mod_entries,
    collect_readiness,
    generate_site,
    render_page,
    render_readiness,
)
from mod_metadata import ReleaseCatalogue, manifest_release_versions


from tests.support import FakeResponse, RoutedSession


MANIFEST = {
    "versions": [
        {"id": "26.3", "type": "release", "releaseTime": "2026-09-15T12:00:00Z"},
        {"id": "26.2", "type": "release", "releaseTime": "2026-06-16T12:00:00Z"},
        {"id": "26.1.2", "type": "release", "releaseTime": "2026-04-09T12:00:00Z"},
        {"id": "26.1.1", "type": "release", "releaseTime": "2026-04-01T12:00:00Z"},
        {"id": "26.1", "type": "release", "releaseTime": "2026-03-24T12:00:00Z"},
        {"id": "26.4-snapshot-1", "type": "snapshot", "releaseTime": "2026-10-01T12:00:00Z"},
    ]
}


def catalogue():
    return ReleaseCatalogue(manifest_release_versions(MANIFEST))


class GenerateSiteTests(unittest.TestCase):
    def test_generate_site_expands_declarations_and_publishes_the_share(self):
        config = {
            "mods": [
                {"id": "known", "type": "modrinth"},
                {"id": "missing", "type": "modrinth"},
                {"id": "github-mod", "type": "github", "repo": "owner/repo", "versionInFileName": True},
            ]
        }
        session = RoutedSession(
            [
                (
                    "/projects",
                    FakeResponse(
                        [
                            {
                                "id": "project-id",
                                "slug": "known",
                                "title": "Known Mod",
                                # A series head and the two series before it.
                                "game_versions": ["26.3", "26.2", "26.1"],
                            },
                            {
                                "id": "github-project-id",
                                "slug": "github-mod",
                                "title": "GitHub Mod Name",
                                "game_versions": [],
                            },
                        ]
                    ),
                ),
                (
                    "/repos/owner/repo/releases",
                    FakeResponse([{"assets": [{"name": "github-mod-mc26.1.1.jar"}]}]),
                ),
                ("version_manifest_v2.json", FakeResponse(MANIFEST)),
            ]
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "mods.yaml"
            template_path = root / "template.html"
            stylesheet_path = root / "style.css"
            output_dir = root / "_site"
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
            template_path.write_text(
                "{{UPDATED_AT}}{{MOD_COUNT}}{{MOD_ROWS}}{{READINESS}}", encoding="utf-8"
            )
            stylesheet_path.write_text("body {}", encoding="utf-8")
            entries = generate_site(
                config_path,
                template_path,
                stylesheet_path,
                output_dir,
                session=session,
                generated_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
            )
            page = (output_dir / "index.html").read_text(encoding="utf-8")
            for name in ["Known Mod", "missing", "GitHub Mod Name"]:
                self.assertIn(name, page)
            self.assertIn('href="https://github.com/owner/repo"', page)
            self.assertIn('href="https://modrinth.com/mod/known"', page)
            self.assertEqual((output_dir / "style.css").read_text(), "body {}")
            # The readiness band is newest release first, and only three chips per row
            # are rendered however many releases a mod turns out to cover.
            self.assertLess(page.index("26.3"), page.index("26.2"))
            self.assertLess(page.index("26.2"), page.index("26.1.2"))
            self.assertNotIn("26.4-snapshot-1", page)
            self.assertEqual(page.count('<li class="v'), 5)

        self.assertEqual([entry.name for entry in entries], ["Known Mod", "missing", "GitHub Mod Name"])
        # A series head stands for its whole series; a jar named for a patch covers
        # that patch and the later members of its series.
        self.assertEqual(entries[0].versions, ["26.3", "26.2", "26.1.2", "26.1.1", "26.1"])
        self.assertEqual(entries[1].versions, [])
        self.assertEqual(entries[2].versions, ["26.1.2", "26.1.1"])
        # The Mojang manifest is fetched once for the whole run, never per mod.
        self.assertEqual(session.count_requests("version_manifest_v2.json"), 1)

    def test_the_readiness_band_counts_the_share_of_mods_behind_each_release(self):
        config = {
            "mods": [
                {"id": "known", "type": "modrinth"},
                {"id": "missing", "type": "modrinth"},
                {"id": "github-mod", "type": "github", "repo": "owner/repo", "versionInFileName": True},
            ]
        }
        session = RoutedSession(
            [
                (
                    "/projects",
                    FakeResponse(
                        [
                            {
                                "id": "project-id",
                                "slug": "known",
                                "title": "Known Mod",
                                "game_versions": ["26.3", "26.2", "26.1"],
                            }
                        ]
                    ),
                ),
                (
                    "/repos/owner/repo/releases",
                    FakeResponse([{"assets": [{"name": "github-mod-mc26.1.1.jar"}]}]),
                ),
                ("version_manifest_v2.json", FakeResponse(MANIFEST)),
            ]
        )
        entries = collect_mod_entries(config, session, catalogue())
        readiness = collect_readiness(catalogue().versions, entries)

        self.assertEqual([item.version for item in readiness], ["26.3", "26.2", "26.1.2"])
        # Only "known" claims 26.3 and 26.2; 26.1.2 additionally has the jar.
        self.assertEqual([item.supported for item in readiness], [1, 1, 2])
        self.assertEqual([item.percent for item in readiness], [33, 33, 67])

    def test_missing_github_repo_returns_no_versions(self):
        config = {
            "mods": [
                {
                    "id": "missing",
                    "type": "github",
                    "repo": "owner/missing",
                    "versionInFileName": True,
                }
            ]
        }
        session = RoutedSession(
            [
                ("/projects", FakeResponse([])),
                ("/repos/owner/missing/releases", FakeResponse({}, 404)),
            ]
        )
        entries = collect_mod_entries(config, session, catalogue())
        self.assertEqual(entries[0].versions, [])
        self.assertEqual(entries[0].name, "missing")

    def test_collect_mod_entries_requires_a_catalogue(self):
        # Passing none has to fail at the call site rather than silently yield no
        # versions, which is why the catalogue is positional.
        with self.assertRaises(TypeError):
            collect_mod_entries({"mods": []}, RoutedSession([]))

    def test_render_page_escapes_content_and_formats_utc8_update_time(self):
        template = "{{UPDATED_AT}}|{{MOD_COUNT}}|{{MOD_ROWS}}"
        entries = [ModEntry('<Unsafe & Mod>', 'https://example.com/?a=1&b="2"', [])]
        rendered = render_page(
            template,
            entries,
            datetime(2026, 7, 17, 0, 5, tzinfo=timezone.utc),
        )
        self.assertIn("2026年07月17日 08:05（UTC+8）", rendered)
        self.assertIn("&lt;Unsafe &amp; Mod&gt;", rendered)
        self.assertIn("a=1&amp;b=&quot;2&quot;", rendered)


class ReadinessTests(unittest.TestCase):
    def test_readiness_takes_newest_releases_first_with_their_share(self):
        entries = [
            ModEntry("a", "u", ["26.2", "26.1.1"]),
            ModEntry("b", "u", ["26.1.1", "26.1"]),
            ModEntry("c", "u", []),
        ]
        # Releases arrive oldest first, as the Mojang manifest orders them.
        readiness = collect_readiness(
            ["26.1", "26.1.1", "26.2", "26.3"], entries
        )
        self.assertEqual(
            [item.version for item in readiness], ["26.3", "26.2", "26.1.1"]
        )
        self.assertEqual([item.supported for item in readiness], [0, 1, 2])
        self.assertEqual([item.percent for item in readiness], [0, 33, 67])

    def test_readiness_counts_releases_beyond_the_rendered_cap(self):
        # Rows show three chips, but the band reads every release a mod covers.
        entries = [ModEntry("a", "u", ["26.3", "26.2", "26.1.2", "26.1.1", "26.1"])]
        readiness = collect_readiness(
            ["26.1", "26.1.1", "26.1.2", "26.2", "26.3"], entries, limit=5
        )
        self.assertEqual([item.supported for item in readiness], [1, 1, 1, 1, 1])

    def test_readiness_ignores_releases_beyond_the_limit(self):
        readiness = collect_readiness(["26.1", "26.1.1", "26.2", "26.3"], [])
        self.assertEqual(len(readiness), 3)

    def test_readiness_percent_is_zero_for_an_empty_catalogue(self):
        self.assertEqual(collect_readiness(["26.3"], [])[0].percent, 0)

    def test_render_readiness_names_the_figure_and_escapes_the_version(self):
        markup = render_readiness([VersionReadiness("<26.3 & x>", 2, 3)])
        self.assertIn("&lt;26.3 &amp; x&gt;", markup)
        self.assertIn("模组兼容 ", markup)
        self.assertIn("67%", markup)

    def test_render_readiness_is_empty_without_releases(self):
        self.assertEqual(render_readiness([]), "")


if __name__ == "__main__":
    unittest.main()
