"""Shared Modrinth and GitHub metadata access helpers."""

from __future__ import annotations

import json
import re
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


MODRINTH_API = "https://api.modrinth.com/v2"
GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT = 20
USER_AGENT = "DHW-PCS/inf-mods site generator"
MINECRAFT_VERSION_IN_FILENAME = re.compile(
    r"(?:^|[-_])mc(\d+(?:\.\d+)+)(?=[-_.]|$)", re.IGNORECASE
)

__all__ = [
    "create_session",
    "extract_github_versions",
    "fetch_json",
    "get_github_releases",
    "get_github_versions",
    "get_mod_from_modrinth",
    "get_modrinth_project_versions",
    "get_modrinth_projects",
    "get_release_game_versions",
    "latest_modrinth_versions",
    "minecraft_version_key",
]


def create_session() -> requests.Session:
    """Create the retrying HTTP session used for metadata collection."""

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET",)),
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def fetch_json(
    session: Any,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    allow_not_found: bool = False,
    timeout: int = REQUEST_TIMEOUT,
) -> Any:
    """Fetch and decode JSON, optionally treating HTTP 404 as missing data."""

    response = session.get(
        url,
        params=params,
        headers=headers,
        timeout=timeout,
    )
    try:
        if allow_not_found and response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    finally:
        response.close()


def get_modrinth_projects(
    session: Any,
    mod_ids: list[str],
    *,
    timeout: int = REQUEST_TIMEOUT,
) -> dict[str, dict[str, Any]]:
    """Return Modrinth projects indexed by both project ID and slug."""

    projects = fetch_json(
        session,
        f"{MODRINTH_API}/projects",
        params={"ids": json.dumps(mod_ids)},
        timeout=timeout,
    )
    by_identifier = {}
    for project in projects:
        by_identifier[project["id"]] = project
        by_identifier[project["slug"]] = project
    return by_identifier


def get_modrinth_project_versions(
    session: Any,
    project_id: str,
    mod_loader: str,
    mc_version: str,
    *,
    timeout: int = REQUEST_TIMEOUT,
) -> list[dict[str, Any]]:
    """Return versions for one Modrinth project and game target."""

    return fetch_json(
        session,
        f"{MODRINTH_API}/project/{project_id}/version",
        params={
            "loaders": f'["{mod_loader}"]',
            "game_versions": f'["{mc_version}"]',
        },
        timeout=timeout,
    )


def get_mod_from_modrinth(
    project_id: str,
    mod_loader: str,
    mc_version: str,
    version_type: str = "release",
    session: Any = requests,
    *,
    timeout: int = REQUEST_TIMEOUT,
) -> tuple[str, str] | None:
    """Return the first matching Modrinth file as ``(filename, URL)``."""

    versions = get_modrinth_project_versions(
        session,
        project_id,
        mod_loader,
        mc_version,
        timeout=timeout,
    )
    for version in versions:
        if version.get("version_type") != version_type:
            continue
        files = version.get("files", [])
        if files:
            return files[0]["filename"], files[0]["url"]
    return None


def get_release_game_versions(
    session: Any,
    *,
    timeout: int = REQUEST_TIMEOUT,
) -> list[str]:
    """Return Modrinth release game versions in newest-first order."""

    versions = fetch_json(
        session,
        f"{MODRINTH_API}/tag/game_version",
        timeout=timeout,
    )
    releases = [version for version in versions if version["version_type"] == "release"]
    releases.sort(key=lambda version: version["date"], reverse=True)
    return [version["version"] for version in releases]


def latest_modrinth_versions(
    project: dict[str, Any] | None,
    release_order: list[str],
) -> list[str]:
    """Return the three newest release versions supported by a project."""

    if project is None:
        return []
    supported = set(project.get("game_versions", []))
    return [version for version in release_order if version in supported][:3]


def minecraft_version_key(version: str) -> tuple[int, ...]:
    """Return a numeric key suitable for sorting release version strings."""

    return tuple(int(part) for part in version.split("."))


def extract_github_versions(releases: list[dict[str, Any]]) -> list[str]:
    """Extract the three newest Minecraft versions from release JAR names."""

    versions = set()
    for release in releases:
        for asset in release.get("assets", []):
            asset_name = asset.get("name", "")
            if not asset_name.lower().endswith(".jar"):
                continue
            match = MINECRAFT_VERSION_IN_FILENAME.search(asset_name)
            if match:
                versions.add(match.group(1))
    return sorted(versions, key=minecraft_version_key, reverse=True)[:3]


def get_github_releases(
    session: Any,
    repo: str,
    github_token: str | None = None,
    *,
    per_page: int | None = None,
    allow_not_found: bool = False,
    timeout: int = REQUEST_TIMEOUT,
) -> list[dict[str, Any]] | None:
    """Return GitHub Releases metadata for a repository."""

    headers = {"Accept": "application/vnd.github+json"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    params = {"per_page": per_page} if per_page is not None else None
    return fetch_json(
        session,
        f"{GITHUB_API}/repos/{repo}/releases",
        params=params,
        headers=headers,
        allow_not_found=allow_not_found,
        timeout=timeout,
    )


def get_github_versions(
    session: Any,
    repo: str,
    github_token: str | None = None,
    *,
    timeout: int = REQUEST_TIMEOUT,
) -> list[str]:
    """Return versions extracted from the latest GitHub release assets."""

    releases = get_github_releases(
        session,
        repo,
        github_token,
        per_page=30,
        allow_not_found=True,
        timeout=timeout,
    )
    return extract_github_versions(releases or [])
