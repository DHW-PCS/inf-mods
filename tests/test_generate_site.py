import tempfile
import unittest

import yaml
from datetime import datetime, timezone
from pathlib import Path

from generate_site import (
    ModEntry,
    collect_mod_entries,
    generate_site,
    render_page,
)


from tests.support import FakeResponse, RoutedSession as FakeSession


class GenerateSiteTests(unittest.TestCase):
    def test_generate_site_preserves_names_versions_links_and_stylesheet(self):
        config = {
            "mods": [
                {"id": "known", "type": "modrinth"},
                {"id": "missing", "type": "modrinth"},
                {"id": "github-mod", "type": "github", "repo": "owner/repo", "versionInFileName": True},
            ]
        }
        session = FakeSession(
            [
                (
                    "/projects",
                    FakeResponse(
                        [
                            {
                                "id": "project-id",
                                "slug": "known",
                                "title": "Known Mod",
                                "game_versions": ["1.21.11"],
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
                    "/tag/game_version",
                    FakeResponse(
                        [
                            {
                                "version": "1.21.11",
                                "version_type": "release",
                                "date": "2025-12-09T12:00:00Z",
                            },
                            {
                                "version": "25w01a",
                                "version_type": "snapshot",
                                "date": "2026-01-02T12:00:00Z",
                            },
                        ]
                    ),
                ),
                (
                    "/repos/owner/repo/releases",
                    FakeResponse([{"assets": [{"name": "github-mod-mc1.21.10.jar"}]}]),
                ),
            ]
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "mods.yaml"
            template_path = root / "template.html"
            stylesheet_path = root / "style.css"
            output_dir = root / "_site"
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
            template_path.write_text("{{UPDATED_AT}}{{MOD_COUNT}}{{MOD_ROWS}}", encoding="utf-8")
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

        self.assertEqual([entry.name for entry in entries], ["Known Mod", "missing", "GitHub Mod Name"])
        self.assertEqual(entries[0].versions, ["1.21.11"])
        self.assertEqual(entries[1].versions, [])
        self.assertEqual(entries[2].versions, ["1.21.10"])

    def test_missing_github_repo_returns_no_versions(self):
        session = FakeSession([("/repos/owner/missing/releases", FakeResponse({}, 404))])
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
        session.responses.insert(0, ("/projects", FakeResponse([])))
        session.responses.insert(
            1,
            (
                "/tag/game_version",
                FakeResponse([]),
            ),
        )
        entries = collect_mod_entries(config, session)
        self.assertEqual(entries[0].versions, [])

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

if __name__ == "__main__":
    unittest.main()
