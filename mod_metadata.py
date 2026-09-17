"""Shared Modrinth and GitHub metadata access helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


MODRINTH_API = "https://api.modrinth.com/v2"
GITHUB_API = "https://api.github.com"
MOJANG_VERSION_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
_VERSION = r"\d+\.\d+(?:\.\d+)*"
_VERSION_END = r"(?![\d.]|-(?:snapshot|pre|rc|beta))"
_VERSION_RANGE = re.compile(r"(?<![\d.])(" + _VERSION + r")\s*[-–—]\s*(" + _VERSION + r")" + _VERSION_END)
_VERSION_WILDCARD = re.compile(r"(?<![\d.])(" + _VERSION + r")\.[xX](?![\w.])")

REQUEST_TIMEOUT = 20
USER_AGENT = "DHW-PCS/inf-mods site generator"
MINECRAFT_VERSION_IN_FILENAME = re.compile(
    r"(?:^|[-_])mc(\d+(?:\.\d+)+)(?=[-_.]|$)(?!-(?:snapshot|pre|rc|beta))", re.IGNORECASE
)

__all__ = [
    "create_session",
    "extract_github_versions",
    "fetch_json",
    "get_github_releases",
    "get_github_versions",
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


def manifest_release_versions(payload: Any) -> list[str]:
    """Validate Mojang metadata and order actual releases by publication time."""
    if not isinstance(payload, dict) or not isinstance(payload.get("versions"), list):
        raise ValueError("Mojang returned an invalid version manifest")
    releases = []
    seen = set()
    for entry in payload["versions"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("type"), str):
            raise ValueError("Mojang returned an invalid version entry")
        if entry["type"] != "release":
            continue
        version = entry.get("id")
        published = entry.get("releaseTime")
        if (
            not isinstance(version, str)
            or not version
            or version in seen
            or not isinstance(published, str)
        ):
            raise ValueError("Mojang returned an invalid release entry")
        date = datetime.fromisoformat(published.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError("Mojang release time must include a timezone")
        seen.add(version)
        releases.append((date, version))
    if not releases:
        raise ValueError("Mojang version manifest contains no releases")
    return [version for _, version in sorted(releases)]


def release_minecraft_versions(name: str, official_versions: list[str] | None = None) -> set[str]:
    """Expand title ranges only through actual Mojang releases, oldest first."""
    text = name.split("Minecraft ", 1)[-1] if "Minecraft " in name else name
    versions = set()

    def expand_range(match):
        if official_versions is None:
            raise ValueError("Mojang version manifest is required to expand a version range")
        start, end = match.groups()
        if start not in official_versions or end not in official_versions:
            raise ValueError("Minecraft range endpoint is absent from the Mojang release manifest")
        left, right = official_versions.index(start), official_versions.index(end)
        if left > right:
            raise ValueError("Minecraft version range is reversed")
        versions.update(official_versions[left : right + 1])
        return " "

    def expand_wildcard(match):
        if official_versions is None:
            raise ValueError("Mojang version manifest is required to expand a version wildcard")
        prefix = match.group(1)
        versions.update(v for v in official_versions if v == prefix or v.startswith(prefix + "."))
        return " "

    text = _VERSION_RANGE.sub(expand_range, text)
    text = _VERSION_WILDCARD.sub(expand_wildcard, text)
    versions.update(re.findall(r"(?<![\d.])" + _VERSION + _VERSION_END, text))
    return versions


def extract_github_versions(
    releases: list[dict[str, Any]],
    *,
    version_in_release: bool = False,
    official_versions: list[str] | None = None
) -> list[str]:
    """Extract the three newest Minecraft versions from JAR names or release titles."""

    versions = set()
    for release in releases:
        if release.get("draft"):
            continue
        if version_in_release:
            if any(asset.get("name", "").endswith(".jar") for asset in release.get("assets", [])):
                versions.update(
                    release_minecraft_versions(release.get("name") or "", official_versions)
                )
            continue
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
    version_in_release: bool = False,
    official_versions: list[str] | None = None,
) -> list[str]:
    """Return versions extracted from the latest GitHub releases."""

    releases = get_github_releases(
        session, repo, github_token, per_page=30, allow_not_found=True, timeout=timeout
    )
    if version_in_release and official_versions is None:
        official_versions = get_mojang_release_versions(session, timeout=timeout)
    return extract_github_versions(
        releases or [], version_in_release=version_in_release, official_versions=official_versions
    )


def get_mojang_release_versions(session: Any, *, timeout: int = REQUEST_TIMEOUT) -> list[str]:
    return manifest_release_versions(fetch_json(session, MOJANG_VERSION_MANIFEST, timeout=timeout))
