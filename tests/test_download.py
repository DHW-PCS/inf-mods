import asyncio
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
import yaml

import download
from download import (
    DownloadBatchError,
    DownloadBatchResult,
    DownloadResult,
    async_download_mods_for_version,
    download_file,
    download_from_file,
    download_mod,
    download_mods,
    download_mods_for_version,
    load_config,
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
    def test_import_has_no_output_or_filesystem_side_effects(self):
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import sys; import download; assert 'yaml' not in sys.modules",
                ],
                cwd=temp_dir,
                env={"PYTHONPATH": str(project_root)},
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "")
            self.assertEqual(completed.stderr, "")
            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_public_api_does_not_include_removed_camel_case_name(self):
        self.assertFalse(hasattr(download, "getModFromModrinth"))
        self.assertNotIn("getModFromModrinth", download.__all__)
        self.assertTrue(
            {
                "DownloadBatchError",
                "DownloadBatchResult",
                "async_download_mods_for_version",
                "download_mods_for_version",
            }.issubset(download.__all__)
        )

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

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            selected = select_modrinth_file(
                {"id": "mod", "type": "modrinth"},
                config,
                session,
            )

        self.assertEqual(selected, ("mod.jar", "https://example.com/mod.jar"))
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(len(session.calls), 4)
        self.assertTrue(
            all(kwargs["timeout"] == 30 for _, kwargs in session.calls)
        )

    def test_download_mod_returns_compatible_beta_fallback_metadata(self):
        session = FakeSession(
            [
                FakeResponse([]),
                FakeResponse([]),
                FakeResponse([]),
                FakeResponse(
                    [
                        {
                            "version_type": "beta",
                            "files": [
                                {
                                    "filename": "mod.jar",
                                    "url": "https://example.com/mod.jar",
                                }
                            ],
                        }
                    ]
                ),
                FakeResponse(content=b"jar data"),
            ]
        )
        config = {
            "mcVersion": "1.21.11",
            "mcCompatibles": ["1.21.10"],
            "modLoader": "fabric",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = download_mod(
                    {"id": "mod", "type": "modrinth"},
                    config,
                    temp_dir,
                    session,
                )

            self.assertTrue(result.success)
            self.assertEqual(result.target_path, Path(temp_dir) / "mod.jar")
            self.assertEqual(result.selected_file, "mod.jar")
            self.assertEqual(result.selected_mc_version, "1.21.10")
            self.assertEqual(result.selected_version_type, "beta")
            self.assertTrue(result.used_fallback)
            self.assertEqual(
                result.notices,
                ("!! Found mod for mod on compatible version 1.21.10",),
            )
            self.assertIsNone(result.error)
            self.assertEqual(output.getvalue(), "")

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
        self.assertEqual(session.calls[0][1]["timeout"], 30)

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

    def test_download_mod_returns_github_compatible_fallback_metadata(self):
        releases = [github_release("Minecraft 1.21.10", "mod.jar")]
        session = FakeSession(
            [
                FakeResponse(releases),
                FakeResponse(content=b"jar data"),
            ]
        )
        config = {
            "mcVersion": "1.21.11",
            "mcCompatibles": ["1.21.10"],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = download_mod(
                    {
                        "id": "github-mod",
                        "type": "github",
                        "repo": "owner/repo",
                        "versionInRelease": True,
                    },
                    config,
                    temp_dir,
                    session,
                )

            self.assertTrue(result.success)
            self.assertEqual(result.source, "github")
            self.assertEqual(result.selected_mc_version, "1.21.10")
            self.assertIsNone(result.selected_version_type)
            self.assertTrue(result.used_fallback)
            self.assertEqual(
                result.notices,
                ("!! Found mod using compatible version 1.21.10",),
            )
            self.assertEqual(output.getvalue(), "")

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
            destination = download_file(
                "../mod.jar",
                "https://example.com/mod.jar",
                output_dir,
                session,
            )

            self.assertEqual(destination, output_dir / "mod.jar")
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

    def test_download_mods_preserves_order_and_isolates_failures(self):
        session = FakeSession(
            [
                FakeResponse([]),
                FakeResponse([]),
                FakeResponse(
                    [
                        {
                            "version_type": "release",
                            "files": [
                                {
                                    "filename": "second.jar",
                                    "url": "https://example.com/second.jar",
                                }
                            ],
                        }
                    ]
                ),
                FakeResponse(content=b"second"),
            ]
        )
        config = {
            "mcVersion": "1.21.11",
            "modLoader": "fabric",
            "mods": [
                {"id": "missing", "type": "modrinth"},
                {"id": "second", "type": "modrinth"},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                results = download_mods(config, temp_dir, session)

            self.assertEqual([result.mod_id for result in results], ["missing", "second"])
            self.assertFalse(results[0].success)
            self.assertTrue(results[1].success)
            self.assertEqual((Path(temp_dir) / "second.jar").read_bytes(), b"second")
            self.assertEqual(output.getvalue(), "")

    def test_versioned_batch_is_strict_and_does_not_mutate_config(self):
        session = FakeSession([FakeResponse([]), FakeResponse([])])
        config = {
            "mcVersion": "1.21.11",
            "mcCompatibles": ["1.21.10"],
            "modLoader": "fabric",
            "mods": [{"id": "missing", "type": "modrinth"}],
        }
        original_config = {
            "mcVersion": "1.21.11",
            "mcCompatibles": ["1.21.10"],
            "modLoader": "fabric",
            "mods": [{"id": "missing", "type": "modrinth"}],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                batch = download_mods_for_version(
                    config,
                    " 1.21.12 ",
                    temp_dir,
                    session=session,
                )

            self.assertEqual(config, original_config)
            self.assertEqual(batch.target_mc_version, "1.21.12")
            self.assertEqual(batch.output_dir, Path(temp_dir))
            self.assertFalse(batch.success)
            self.assertEqual(
                [result.mod_id for result in batch.failures],
                ["missing"],
            )
            self.assertEqual(len(session.calls), 2)
            for url, kwargs in session.calls:
                self.assertIn("game_versions", kwargs["params"])
                self.assertEqual(kwargs["params"]["game_versions"], '["1.21.12"]')
            self.assertEqual(output.getvalue(), "")

            serialized = batch.as_dict()
            self.assertEqual(serialized["target_mc_version"], "1.21.12")
            self.assertEqual(serialized["output_dir"], temp_dir)
            self.assertFalse(serialized["success"])
            self.assertEqual(serialized["results"][0]["notices"], [])
            json.dumps(serialized)

            with self.assertRaises(DownloadBatchError) as raised:
                batch.raise_for_failures()

            self.assertIs(raised.exception.result, batch)
            self.assertIn("missing: no matching file", str(raised.exception))

    def test_versioned_batch_uses_only_explicit_compatible_versions(self):
        session = FakeSession(
            [
                FakeResponse([]),
                FakeResponse([]),
                FakeResponse(
                    [
                        {
                            "version_type": "release",
                            "files": [
                                {
                                    "filename": "mod.jar",
                                    "url": "https://example.com/mod.jar",
                                }
                            ],
                        }
                    ]
                ),
                FakeResponse(content=b"jar data"),
            ]
        )
        config = {
            "mcVersion": "1.21.11",
            "mcCompatibles": ["1.21.9"],
            "modLoader": "fabric",
            "mods": [{"id": "mod", "type": "modrinth"}],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            batch = download_mods_for_version(
                config,
                "1.21.12",
                temp_dir,
                compatible_versions=["1.21.11", "1.21.11", "1.21.12"],
                session=session,
            )

            self.assertTrue(batch.success)
            batch.raise_for_failures()
            self.assertEqual(batch.failures, ())
            self.assertEqual(batch.results[0].selected_mc_version, "1.21.11")
            self.assertTrue(batch.results[0].used_fallback)
            self.assertEqual(
                batch.results[0].notices,
                ("!! Found mod for mod on compatible version 1.21.11",),
            )
            self.assertEqual((Path(temp_dir) / "mod.jar").read_bytes(), b"jar data")

    def test_async_versioned_batch_uses_the_same_structured_contract(self):
        session = FakeSession(
            [
                FakeResponse(
                    [
                        {
                            "version_type": "release",
                            "files": [
                                {
                                    "filename": "mod.jar",
                                    "url": "https://example.com/mod.jar",
                                }
                            ],
                        }
                    ]
                ),
                FakeResponse(content=b"jar data"),
            ]
        )
        config = {
            "mcVersion": "old",
            "modLoader": "fabric",
            "mods": [{"id": "mod", "type": "modrinth"}],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                batch = asyncio.run(
                    async_download_mods_for_version(
                        config,
                        "1.21.12",
                        temp_dir,
                        session=session,
                    )
                )

            self.assertIsInstance(batch, DownloadBatchResult)
            self.assertTrue(batch.success)
            self.assertEqual(batch.results[0].selected_mc_version, "1.21.12")
            self.assertEqual(output.getvalue(), "")

    def test_versioned_batch_rejects_invalid_version_arguments(self):
        with self.assertRaisesRegex(ValueError, "target Minecraft version"):
            download_mods_for_version({}, " ")
        with self.assertRaisesRegex(ValueError, "compatible_versions"):
            download_mods_for_version(
                {},
                "1.21.12",
                compatible_versions="1.21.11",
            )

    def test_download_mod_converts_request_error_to_result(self):
        session = FakeSession([FakeResponse(status_code=503)])

        result = download_mod(
            {"id": "broken", "type": "modrinth"},
            {"mcVersion": "1.21.11", "modLoader": "fabric"},
            session=session,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.mod_id, "broken")
        self.assertEqual(result.source, "modrinth")
        self.assertEqual(result.error, "HTTP 503")

    def test_load_config_and_download_from_file_support_yaml_paths(self):
        config = {
            "mcVersion": "1.21.11",
            "modLoader": "fabric",
            "mods": [{"id": "mod", "type": "modrinth"}],
        }
        session = FakeSession(
            [
                FakeResponse(
                    [
                        {
                            "version_type": "release",
                            "files": [
                                {
                                    "filename": "mod.jar",
                                    "url": "https://example.com/mod.jar",
                                }
                            ],
                        }
                    ]
                ),
                FakeResponse(content=b"jar data"),
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "custom.yaml"
            output_dir = Path(temp_dir) / "custom-mods"
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

            self.assertEqual(load_config(config_path), config)
            results = download_from_file(config_path, output_dir, session)

            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].success)
            self.assertEqual(results[0].target_path, output_dir / "mod.jar")

    def test_load_config_rejects_non_mapping_yaml(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "invalid.yaml"
            config_path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "must be a mapping"):
                load_config(config_path)

    def test_main_renders_existing_cli_messages(self):
        results = [
            DownloadResult(
                mod_id="fallback",
                source="modrinth",
                success=True,
                target_path=Path("mods/fallback.jar"),
                selected_file="fallback.jar",
                selected_mc_version="1.21.10",
                selected_version_type="release",
                used_fallback=True,
                notices=(
                    "!! Found mod for fallback on compatible version 1.21.10",
                ),
            ),
            DownloadResult(
                mod_id="missing",
                source="github",
                success=False,
            ),
            DownloadResult(
                mod_id="broken",
                source="modrinth",
                success=False,
                error="HTTP 503",
            ),
        ]

        output = io.StringIO()
        mods = [{"id": result.mod_id} for result in results]
        with patch("download.load_config", return_value={"mods": mods}) as load_mock:
            with patch("download.download_mod", side_effect=results) as download_mock:
                with contextlib.redirect_stdout(output):
                    download.main()

        load_mock.assert_called_once_with(Path("mods.yaml"))
        self.assertEqual(
            download_mock.call_args_list,
            [
                unittest.mock.call(mod, {"mods": mods}, Path("mods"))
                for mod in mods
            ],
        )
        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "!! Found mod for fallback on compatible version 1.21.10",
                "!! Failed to download missing",
                "!! Failed to download broken: HTTP 503",
            ],
        )


if __name__ == "__main__":
    unittest.main()
