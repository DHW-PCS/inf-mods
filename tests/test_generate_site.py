import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import requests

from generate_site import (
    ModEntry,
    collect_mod_entries,
    extract_github_versions,
    generate_site,
    latest_modrinth_versions,
    render_page,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = responses

    def get(self, url, **kwargs):
        for url_part, response in self.responses:
            if url_part in url:
                return response
        raise AssertionError(f"Unexpected request: {url}")


class GenerateSiteTests(unittest.TestCase):
    def test_latest_modrinth_versions_follow_release_order(self):
        project = {"game_versions": ["1.21.9", "26.1.1", "1.21.11", "24w14a"]}
        release_order = ["26.2", "26.1.1", "1.21.11", "1.21.10", "1.21.9"]
        self.assertEqual(
            latest_modrinth_versions(project, release_order),
            ["26.1.1", "1.21.11", "1.21.9"],
        )

    def test_github_versions_are_filtered_deduplicated_and_sorted(self):
        releases = [
            {
                "assets": [
                    {"name": "mod-v1-mc1.21.9.jar"},
                    {"name": "mod-v2-mc1.21.11.jar"},
                    {"name": "mod-v2-mc1.21.11.jar"},
                    {"name": "mod-v3-mc26.1.1-fabric.jar"},
                    {"name": "mod-v3-mc99.0.zip"},
                    {"name": "sources.jar"},
                ]
            }
        ]
        self.assertEqual(
            extract_github_versions(releases),
            ["26.1.1", "1.21.11", "1.21.9"],
        )

    def test_collect_entries_uses_title_and_falls_back_to_id(self):
        config = {
            "mods": [
                {"id": "known", "type": "modrinth"},
                {"id": "missing", "type": "modrinth"},
                {
                    "id": "github-mod",
                    "type": "github",
                    "repo": "owner/repo",
                    "versionInFileName": True,
                },
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

        entries = collect_mod_entries(config, session)

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
        self.assertIn("暂无版本信息", rendered)

    def test_generate_site_writes_static_page_and_stylesheet(self):
        config = {"mods": [{"id": "known", "type": "modrinth"}]}
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
                            }
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
                            }
                        ]
                    ),
                ),
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "mods.yaml"
            template_path = root / "template.html"
            stylesheet_path = root / "style.css"
            output_dir = root / "_site"
            config_path.write_text(
                "mods:\n- id: known\n  type: modrinth\n",
                encoding="utf-8",
            )
            template_path.write_text(
                "<title>DHW Inf 模组详情</title>{{UPDATED_AT}}{{MOD_COUNT}}{{MOD_ROWS}}",
                encoding="utf-8",
            )
            stylesheet_path.write_text("body {}", encoding="utf-8")

            generate_site(
                config_path,
                template_path,
                stylesheet_path,
                output_dir,
                session=session,
                generated_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
            )

            page = (output_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("Known Mod", page)
            self.assertNotIn("<script", page.lower())
            self.assertEqual((output_dir / "style.css").read_text(), "body {}")


if __name__ == "__main__":
    unittest.main()
