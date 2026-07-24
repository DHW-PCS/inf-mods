from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import requests

from mod_metadata import (
    get_github_releases,
    get_mod_from_modrinth as _get_mod_from_modrinth,
)

REQUEST_TIMEOUT = 30

__all__ = [
    "DownloadBatchError",
    "DownloadBatchResult",
    "DownloadResult",
    "async_download_mods_for_version",
    "download_file",
    "download_from_file",
    "download_mod",
    "download_mods",
    "download_mods_for_version",
    "get_mod_from_modrinth",
    "load_config",
    "main",
    "select_github_file",
    "select_modrinth_file",
]


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """The outcome of downloading one configured mod."""

    mod_id: str
    source: str
    success: bool
    target_path: Path | None = None
    selected_file: str | None = None
    selected_mc_version: str | None = None
    selected_version_type: str | None = None
    used_fallback: bool = False
    notices: tuple[str, ...] = ()
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of this result."""

        return {
            "mod_id": self.mod_id,
            "source": self.source,
            "success": self.success,
            "target_path": str(self.target_path) if self.target_path else None,
            "selected_file": self.selected_file,
            "selected_mc_version": self.selected_mc_version,
            "selected_version_type": self.selected_version_type,
            "used_fallback": self.used_fallback,
            "notices": list(self.notices),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class DownloadBatchResult:
    """The complete result of staging mods for one Minecraft version."""

    target_mc_version: str
    output_dir: Path
    results: tuple[DownloadResult, ...]

    @property
    def success(self) -> bool:
        return all(result.success for result in self.results)

    @property
    def failures(self) -> tuple[DownloadResult, ...]:
        return tuple(result for result in self.results if not result.success)

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of this batch."""

        return {
            "target_mc_version": self.target_mc_version,
            "output_dir": str(self.output_dir),
            "success": self.success,
            "results": [result.as_dict() for result in self.results],
        }

    def raise_for_failures(self) -> None:
        """Raise with the full batch result when any mod failed."""

        if self.failures:
            raise DownloadBatchError(self)


class DownloadBatchError(RuntimeError):
    """Raised when a versioned batch contains one or more failed mods."""

    def __init__(self, result: DownloadBatchResult):
        self.result = result
        details = ", ".join(
            f"{failure.mod_id}: {failure.error or 'no matching file'}"
            for failure in result.failures
        )
        super().__init__(
            f"{len(result.failures)} mod(s) failed for Minecraft "
            f"{result.target_mc_version}: {details}"
        )


@dataclass(frozen=True, slots=True)
class _SelectedFile:
    filename: str
    url: str
    mc_version: str | None = None
    version_type: str | None = None
    used_fallback: bool = False
    notices: tuple[str, ...] = ()

    def as_pair(self) -> tuple[str, str]:
        return self.filename, self.url


def load_config(path: str | os.PathLike[str] = Path("mods.yaml")) -> dict[str, Any]:
    """Load a YAML downloader configuration from *path*."""

    try:
        import yaml
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "PyYAML is required to load a YAML configuration; "
            "install the dependencies from requirements.txt or pass a config mapping"
        ) from error

    with Path(path).open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file) or {}
    if not isinstance(config, dict):
        raise ValueError("mod configuration must be a mapping")
    return config


def get_mod_from_modrinth(
    project_id: str,
    mod_loader: str,
    mc_version: str,
    version_type: str = "release",
    session: Any = requests,
) -> tuple[str, str] | None:
    """Return the first matching Modrinth file as ``(filename, URL)``."""

    return _get_mod_from_modrinth(
        project_id,
        mod_loader,
        mc_version,
        version_type,
        session=session,
        timeout=REQUEST_TIMEOUT,
    )


def _select_modrinth_file(
    mod: Mapping[str, Any],
    config: Mapping[str, Any],
    session: Any,
) -> _SelectedFile | None:
    mod_id = mod["id"]
    loader = config["modLoader"]
    preferred_type = mod.get("versionType", "release")

    versions = [config["mcVersion"], *config.get("mcCompatibles", [])]
    version_types = [preferred_type]
    if preferred_type != "beta":
        version_types.append("beta")

    for version_index, mc_version in enumerate(versions):
        for version_type in version_types:
            mod_file = get_mod_from_modrinth(
                mod_id,
                loader,
                mc_version,
                version_type,
                session=session,
            )
            if not mod_file:
                continue

            notices: tuple[str, ...] = ()
            if version_index:
                notices = (
                    f"!! Found mod for {mod_id} on compatible version {mc_version}",
                )
            elif version_type == "beta" and preferred_type != "beta":
                notices = (f"!! Found beta version for {mod_id} on {mc_version}",)

            return _SelectedFile(
                *mod_file,
                mc_version=mc_version,
                version_type=version_type,
                used_fallback=version_index > 0 or version_type != preferred_type,
                notices=notices,
            )
    return None


def select_modrinth_file(
    mod: Mapping[str, Any],
    config: Mapping[str, Any],
    session: Any = requests,
) -> tuple[str, str] | None:
    """Select a Modrinth file without downloading it or printing output."""

    selected = _select_modrinth_file(mod, config, session)
    return selected.as_pair() if selected else None


def _first_jar(releases: list[dict[str, Any]]) -> tuple[str, str] | None:
    for release in releases:
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            if name.lower().endswith(".jar"):
                return name, asset["browser_download_url"]
    return None


def _first_jar_matching(
    releases: list[dict[str, Any]],
    text: str,
) -> tuple[str, str] | None:
    for release in releases:
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            if name.lower().endswith(".jar") and text in name:
                return name, asset["browser_download_url"]
    return None


def _select_github_file(
    mod: Mapping[str, Any],
    config: Mapping[str, Any],
    session: Any,
) -> _SelectedFile | None:
    releases = get_github_releases(
        session,
        mod["repo"],
        timeout=REQUEST_TIMEOUT,
    )
    if not isinstance(releases, list):
        return None

    release_filter = mod.get("releaseFilter")
    if release_filter:
        matching_releases = [
            release
            for release in releases
            if release_filter in (release.get("name") or "")
        ]
        mod_file = _first_jar(matching_releases[:1])
        return _SelectedFile(*mod_file) if mod_file else None

    compatible_versions = config.get("mcCompatibles", [])
    if mod.get("versionInRelease"):
        versions = [config["mcVersion"], *compatible_versions]
        for index, version in enumerate(versions):
            matching_releases = [
                release
                for release in releases
                if version in (release.get("name") or "")
            ]
            mod_file = _first_jar(matching_releases[:1])
            if mod_file:
                notices = (
                    (f"!! Found mod using compatible version {version}",)
                    if index
                    else ()
                )
                return _SelectedFile(
                    *mod_file,
                    mc_version=version,
                    used_fallback=index > 0,
                    notices=notices,
                )
        return None

    version_filter = None
    selected_mc_version = None
    if mod.get("versionInFileName"):
        version_filter = config["mcVersion"]
        selected_mc_version = config["mcVersion"]
    elif mod.get("versionFilter"):
        version_filter = mod["versionFilter"]

    if not version_filter:
        return None

    mod_file = _first_jar_matching(releases, version_filter)
    if mod_file:
        return _SelectedFile(*mod_file, mc_version=selected_mc_version)

    for version in compatible_versions:
        mod_file = _first_jar_matching(releases, version)
        if mod_file:
            return _SelectedFile(
                *mod_file,
                mc_version=version,
                used_fallback=True,
                notices=(f"!! Found mod using compatible version {version}",),
            )
    return None


def select_github_file(
    mod: Mapping[str, Any],
    config: Mapping[str, Any],
    session: Any = requests,
) -> tuple[str, str] | None:
    """Select a GitHub Releases file without downloading it or printing output."""

    selected = _select_github_file(mod, config, session)
    return selected.as_pair() if selected else None


def download_file(
    filename: str,
    url: str,
    output_dir: str | os.PathLike[str],
    session: Any = requests,
) -> Path:
    """Download one file atomically and return its final path."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    destination = output_path / Path(filename).name
    temporary = destination.with_name(f".{destination.name}.part")

    response = session.get(
        url,
        allow_redirects=True,
        stream=True,
        timeout=REQUEST_TIMEOUT,
    )
    try:
        response.raise_for_status()
        with temporary.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)
        os.replace(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)
        response.close()


def download_mod(
    mod: Mapping[str, Any],
    config: Mapping[str, Any],
    output_dir: str | os.PathLike[str] = Path("mods"),
    session: Any = requests,
) -> DownloadResult:
    """Download one mod and return a result instead of printing or raising."""

    mod_id = str(mod.get("id", "<unknown>"))
    source = str(mod.get("type", ""))
    selected: _SelectedFile | None = None

    try:
        if source == "modrinth":
            selected = _select_modrinth_file(mod, config, session)
        elif source == "github" and mod.get("repo"):
            selected = _select_github_file(mod, config, session)

        if not selected:
            return DownloadResult(
                mod_id=mod_id,
                source=source,
                success=False,
            )

        target_path = download_file(
            selected.filename,
            selected.url,
            output_dir,
            session=session,
        )
        return DownloadResult(
            mod_id=mod_id,
            source=source,
            success=True,
            target_path=target_path,
            selected_file=selected.filename,
            selected_mc_version=selected.mc_version,
            selected_version_type=selected.version_type,
            used_fallback=selected.used_fallback,
            notices=selected.notices,
        )
    except (KeyError, TypeError, ValueError, requests.RequestException) as error:
        return DownloadResult(
            mod_id=mod_id,
            source=source,
            success=False,
            selected_file=selected.filename if selected else None,
            selected_mc_version=selected.mc_version if selected else None,
            selected_version_type=selected.version_type if selected else None,
            used_fallback=selected.used_fallback if selected else False,
            notices=selected.notices if selected else (),
            error=str(error),
        )


def download_mods(
    config: Mapping[str, Any],
    output_dir: str | os.PathLike[str] = Path("mods"),
    session: Any = requests,
) -> list[DownloadResult]:
    """Download all configured mods in order and return their results."""

    return [
        download_mod(mod, config, output_dir, session=session)
        for mod in config.get("mods", [])
    ]


def _normalise_mc_version(value: str, description: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{description} must be a non-empty string")
    return value.strip()


def _normalise_compatible_versions(
    versions: Sequence[str],
    target_mc_version: str,
) -> tuple[str, ...]:
    if isinstance(versions, (str, bytes)):
        raise ValueError("compatible_versions must be a sequence of version strings")

    normalised: list[str] = []
    for version in versions:
        candidate = _normalise_mc_version(version, "compatible version")
        if candidate != target_mc_version and candidate not in normalised:
            normalised.append(candidate)
    return tuple(normalised)


def download_mods_for_version(
    config: Mapping[str, Any],
    mc_version: str,
    output_dir: str | os.PathLike[str] = Path("mods"),
    *,
    compatible_versions: Sequence[str] = (),
    session: Any = requests,
) -> DownloadBatchResult:
    """Download a complete mod batch for an explicitly selected game version.

    The supplied configuration is not mutated. Its ``mcCompatibles`` value is
    ignored unless replacement versions are passed through
    ``compatible_versions``.
    """

    target_mc_version = _normalise_mc_version(
        mc_version,
        "target Minecraft version",
    )
    fallback_versions = _normalise_compatible_versions(
        compatible_versions,
        target_mc_version,
    )
    effective_config = dict(config)
    effective_config["mcVersion"] = target_mc_version
    effective_config["mcCompatibles"] = list(fallback_versions)
    target_dir = Path(output_dir)
    results = download_mods(
        effective_config,
        output_dir=target_dir,
        session=session,
    )
    return DownloadBatchResult(
        target_mc_version=target_mc_version,
        output_dir=target_dir,
        results=tuple(results),
    )


async def async_download_mods_for_version(
    config: Mapping[str, Any],
    mc_version: str,
    output_dir: str | os.PathLike[str] = Path("mods"),
    *,
    compatible_versions: Sequence[str] = (),
    session: Any = requests,
) -> DownloadBatchResult:
    """Run :func:`download_mods_for_version` without blocking an event loop."""

    return await asyncio.to_thread(
        download_mods_for_version,
        config,
        mc_version,
        output_dir,
        compatible_versions=compatible_versions,
        session=session,
    )


def download_from_file(
    config_path: str | os.PathLike[str] = Path("mods.yaml"),
    output_dir: str | os.PathLike[str] = Path("mods"),
    session: Any = requests,
) -> list[DownloadResult]:
    """Load a YAML configuration and download all of its mods."""

    return download_mods(
        load_config(config_path),
        output_dir=output_dir,
        session=session,
    )


def _print_cli_result(result: DownloadResult) -> None:
    for notice in result.notices:
        print(notice)
    if not result.success:
        if result.error:
            print(f"!! Failed to download {result.mod_id}: {result.error}")
        else:
            print("!! Failed to download", result.mod_id)


def main(
    config_path: str | os.PathLike[str] = Path("mods.yaml"),
    output_dir: str | os.PathLike[str] = Path("mods"),
) -> None:
    """Run the existing no-argument command-line workflow."""

    config = load_config(config_path)
    for mod in config.get("mods", []):
        _print_cli_result(download_mod(mod, config, output_dir))


if __name__ == "__main__":
    main()
