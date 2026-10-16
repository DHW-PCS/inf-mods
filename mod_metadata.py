"""Shared Modrinth and GitHub metadata access helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Iterable

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
# A bare declaration has to be a whole release token; anything else is noise such
# as the "26.3-pre-1" and "26.4-snapshot-1" strings Modrinth mixes into its lists.
_RELEASE_TOKEN = re.compile(r"\d+(?:\.\d+)+")
SERIES_DEPTH = 2

REQUEST_TIMEOUT = 20
USER_AGENT = "DHW-PCS/inf-mods site generator"
MINECRAFT_VERSION_IN_FILENAME = re.compile(
    r"(?:^|[-_])mc(\d+(?:\.\d+)+)(?=[-_.]|$)(?!-(?:snapshot|pre|rc|beta))", re.IGNORECASE
)

__all__ = [
    "ReleaseCatalogue",
    "create_session",
    "extract_github_versions",
    "fetch_json",
    "get_github_releases",
    "get_github_versions",
    "get_modrinth_projects",
    "get_mojang_release_versions",
    "load_release_catalogue",
    "manifest_release_versions",
    "modrinth_supported_versions",
    "release_minecraft_versions",
    "version_series",
]


def version_series(version: str) -> str:
    """Return the release series a version belongs to, so "26.1.2" names "26.1"."""

    return ".".join(version.split(".")[:SERIES_DEPTH])


class ReleaseCatalogue:
    """The official releases from the Mojang manifest, the only authority on versions.

    Every decision about compatibility is a set operation over the real releases held
    here. Strings only ever look a version up; they never decide whether one is newer,
    which is why ordering comes from the manifest rather than from comparing numbers.
    """

    def __init__(self, versions: Iterable[str]) -> None:
        self.versions = tuple(versions)
        self._rank = {version: index for index, version in enumerate(self.versions)}
        series: dict[str, list[str]] = {}
        for version in self.versions:
            series.setdefault(version_series(version), []).append(version)
        self._series = series

    def series_members(self, version: str) -> set[str]:
        """Every release sharing a version's series, which is what a wildcard names."""

        return set(self._series.get(version_series(version), ()))

    def newest_first(self, versions: Iterable[str]) -> list[str]:
        """Order releases the way the manifest does, newest publication first."""

        return sorted(versions, key=self._rank.__getitem__, reverse=True)

    def span(self, start: str, end: str) -> set[str]:
        """The releases from start to end inclusive, following manifest order."""

        if start not in self._rank or end not in self._rank:
            raise ValueError("Minecraft range endpoint is absent from the Mojang release manifest")
        left, right = self._rank[start], self._rank[end]
        if left > right:
            raise ValueError("Minecraft version range is reversed")
        return set(self.versions[left : right + 1])

    def covering(self, version: str) -> set[str]:
        """The releases a single declared version stands for.

        A two-part version names a series head, so it stands for that whole series.
        A longer one has to be a real release to have a position at all, and then it
        stands for itself plus the later releases of the same series, never the earlier
        ones: a mod built for 26.1.2 is not thereby built for 26.1.1.
        """

        members = self._series.get(version_series(version))
        if not members:
            return set()
        if len(version.split(".")) == SERIES_DEPTH:
            return set(members)
        if version not in self._rank:
            return set()
        floor = self._rank[version]
        return {member for member in members if self._rank[member] >= floor}

    def support(self, declarations: Iterable[str]) -> list[str]:
        """Expand declared release versions into the real releases they cover."""

        covered: set[str] = set()
        for declaration in declarations:
            # Anything that is not wholly a release token is noise and is dropped
            # rather than failed on, so one odd entry cannot take the site down.
            if isinstance(declaration, str) and _RELEASE_TOKEN.fullmatch(declaration):
                covered |= self.covering(declaration)
        return self.newest_first(covered)


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


def modrinth_supported_versions(
    project: dict[str, Any] | None,
    catalogue: ReleaseCatalogue,
) -> list[str]:
    """Return every release a Modrinth project's game versions cover, newest first."""

    if project is None:
        return []
    return catalogue.support(project.get("game_versions", []))


def manifest_release_versions(payload: Any) -> list[str]:
    """Validate Mojang metadata and order actual releases by publication time."""
    if not isinstance(payload, dict) or not isinstance(payload.get("versions"), list):
        raise ValueError("Mojang returned an invalid version manifest")
    releases = []
    seen = set()
    for position, entry in enumerate(payload["versions"]):
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
        releases.append((date, position, version))
    if not releases:
        raise ValueError("Mojang version manifest contains no releases")
    # The manifest array lists the newest release first, so a later position is an older
    # release. That settles the one releaseTime tie Mojang has shipped, and the version
    # string never gets a say in the order.
    ordered = sorted(releases, key=lambda release: (release[0], -release[1]))
    return [version for _, _, version in ordered]


def load_release_catalogue(session: Any, *, timeout: int = REQUEST_TIMEOUT) -> ReleaseCatalogue:
    """Build the release catalogue from a freshly fetched Mojang manifest."""

    return ReleaseCatalogue(get_mojang_release_versions(session, timeout=timeout))


def release_minecraft_versions(name: str, catalogue: ReleaseCatalogue) -> list[str]:
    """Read the Minecraft versions a release title names, newest release first.

    Ranges are the manifest span between their endpoints and nothing more: an explicit
    upper bound is a statement the mod author made deliberately. Bare versions fall
    back to the series default that ``ReleaseCatalogue.covering`` describes.
    """
    text = name.split("Minecraft ", 1)[-1] if "Minecraft " in name else name
    versions = set()

    def absorb_range(match):
        versions.update(catalogue.span(*match.groups()))
        return " "

    def absorb_wildcard(match):
        versions.update(catalogue.series_members(match.group(1)))
        return " "

    text = _VERSION_RANGE.sub(absorb_range, text)
    text = _VERSION_WILDCARD.sub(absorb_wildcard, text)
    for version in re.findall(r"(?<![\d.])" + _VERSION + _VERSION_END, text):
        versions.update(catalogue.covering(version))
    return catalogue.newest_first(versions)


def extract_github_versions(
    releases: list[dict[str, Any]],
    catalogue: ReleaseCatalogue,
    *,
    version_in_release: bool = False,
) -> list[str]:
    """Return every release the latest GitHub releases claim, newest first."""

    versions = set()
    for release in releases:
        if release.get("draft"):
            continue
        assets = release.get("assets", [])
        if version_in_release:
            if any(asset.get("name", "").endswith(".jar") for asset in assets):
                versions.update(
                    release_minecraft_versions(release.get("name") or "", catalogue)
                )
            continue
        for asset in assets:
            asset_name = asset.get("name", "")
            if not asset_name.lower().endswith(".jar"):
                continue
            match = MINECRAFT_VERSION_IN_FILENAME.search(asset_name)
            if match:
                versions.update(catalogue.covering(match.group(1)))
    return catalogue.newest_first(versions)


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
    catalogue: ReleaseCatalogue,
    github_token: str | None = None,
    *,
    timeout: int = REQUEST_TIMEOUT,
    version_in_release: bool = False,
) -> list[str]:
    """Return the versions claimed by the latest GitHub releases of a repository."""

    releases = get_github_releases(
        session, repo, github_token, per_page=30, allow_not_found=True, timeout=timeout
    )
    return extract_github_versions(
        releases or [], catalogue, version_in_release=version_in_release
    )


def get_mojang_release_versions(session: Any, *, timeout: int = REQUEST_TIMEOUT) -> list[str]:
    return manifest_release_versions(fetch_json(session, MOJANG_VERSION_MANIFEST, timeout=timeout))
