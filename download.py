import os
from pathlib import Path

import requests
import yaml


MODRINTH_VERSIONS_URL = "https://api.modrinth.com/v2/project/{project_id}/version"
GITHUB_RELEASES_URL = "https://api.github.com/repos/{repo}/releases"
REQUEST_TIMEOUT = 30


def _get_json(session, url, **kwargs):
    response = session.get(url, timeout=REQUEST_TIMEOUT, **kwargs)
    try:
        response.raise_for_status()
        return response.json()
    finally:
        response.close()


def get_mod_from_modrinth(
    project_id,
    mod_loader,
    mc_version,
    version_type="release",
    session=requests,
):
    versions = _get_json(
        session,
        MODRINTH_VERSIONS_URL.format(project_id=project_id),
        params={
            "loaders": f'["{mod_loader}"]',
            "game_versions": f'["{mc_version}"]',
        },
    )

    for version in versions:
        if version.get("version_type") != version_type:
            continue
        files = version.get("files", [])
        if files:
            return files[0]["filename"], files[0]["url"]
    return None


# Keep the original public name for callers that import this script.
def getModFromModrinth(id, modLoader, mcVersion, versionType="release"):
    return get_mod_from_modrinth(id, modLoader, mcVersion, versionType)


def select_modrinth_file(mod, config, session=requests):
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
            if version_index:
                print(f"!! Found mod for {mod_id} on compatible version {mc_version}")
            elif version_type == "beta" and preferred_type != "beta":
                print(f"!! Found beta version for {mod_id} on {mc_version}")
            return mod_file
    return None


def _first_jar(releases):
    for release in releases:
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            if name.lower().endswith(".jar"):
                return name, asset["browser_download_url"]
    return None


def _first_jar_matching(releases, text):
    for release in releases:
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            if name.lower().endswith(".jar") and text in name:
                return name, asset["browser_download_url"]
    return None


def select_github_file(mod, config, session=requests):
    releases = _get_json(
        session,
        GITHUB_RELEASES_URL.format(repo=mod["repo"]),
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
        return _first_jar(matching_releases[:1])

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
                if index:
                    print(f"!! Found mod using compatible version {version}")
                return mod_file
        return None

    version_filter = None
    if mod.get("versionInFileName"):
        version_filter = config["mcVersion"]
    elif mod.get("versionFilter"):
        version_filter = mod["versionFilter"]

    if not version_filter:
        return None

    mod_file = _first_jar_matching(releases, version_filter)
    if mod_file:
        return mod_file

    for version in compatible_versions:
        mod_file = _first_jar_matching(releases, version)
        if mod_file:
            print(f"!! Found mod using compatible version {version}")
            return mod_file
    return None


def download_file(filename, url, output_dir, session=requests):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / Path(filename).name
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
    finally:
        temporary.unlink(missing_ok=True)
        response.close()


def download_mods(config, output_dir=Path("mods"), session=requests):
    for mod in config.get("mods", []):
        mod_file = None
        try:
            if mod.get("type") == "modrinth":
                mod_file = select_modrinth_file(mod, config, session=session)
            elif mod.get("type") == "github" and mod.get("repo"):
                mod_file = select_github_file(mod, config, session=session)

            if mod_file:
                download_file(*mod_file, output_dir, session=session)
            else:
                print("!! Failed to download", mod.get("id", "<unknown>"))
        except (KeyError, TypeError, ValueError, requests.RequestException) as error:
            print(f'!! Failed to download {mod.get("id", "<unknown>")}: {error}')


def main(config_path=Path("mods.yaml"), output_dir=Path("mods")):
    with config_path.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file) or {}
    download_mods(config, output_dir)


if __name__ == "__main__":
    main()
