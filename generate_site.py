import argparse
import html
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


MODRINTH_API = "https://api.modrinth.com/v2"
GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT = 20
USER_AGENT = "DHW-PCS/inf-mods site generator"
MINECRAFT_VERSION_IN_FILENAME = re.compile(
    r"(?:^|[-_])mc(\d+(?:\.\d+)+)(?=[-_.]|$)", re.IGNORECASE
)


@dataclass(frozen=True)
class ModEntry:
    name: str
    url: str
    versions: list[str]


def create_session() -> requests.Session:
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


def fetch_json(session, url, *, params=None, headers=None, allow_not_found=False):
    response = session.get(
        url,
        params=params,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    if allow_not_found and response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    if not isinstance(config, dict) or not isinstance(config.get("mods"), list):
        raise ValueError("mods.yaml must contain a mods list")
    return config


def get_modrinth_projects(session, mod_ids: list[str]) -> dict[str, dict]:
    projects = fetch_json(
        session,
        f"{MODRINTH_API}/projects",
        params={"ids": json.dumps(mod_ids)},
    )
    by_identifier = {}
    for project in projects:
        by_identifier[project["id"]] = project
        by_identifier[project["slug"]] = project
    return by_identifier


def get_release_game_versions(session) -> list[str]:
    versions = fetch_json(session, f"{MODRINTH_API}/tag/game_version")
    releases = [version for version in versions if version["version_type"] == "release"]
    releases.sort(key=lambda version: version["date"], reverse=True)
    return [version["version"] for version in releases]


def latest_modrinth_versions(project: dict | None, release_order: list[str]) -> list[str]:
    if project is None:
        return []
    supported = set(project.get("game_versions", []))
    return [version for version in release_order if version in supported][:3]


def minecraft_version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def extract_github_versions(releases: list[dict]) -> list[str]:
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


def get_github_versions(session, repo: str, github_token: str | None) -> list[str]:
    headers = {"Accept": "application/vnd.github+json"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    releases = fetch_json(
        session,
        f"{GITHUB_API}/repos/{repo}/releases",
        params={"per_page": 30},
        headers=headers,
        allow_not_found=True,
    )
    return extract_github_versions(releases or [])


def collect_mod_entries(config: dict, session, github_token: str | None = None) -> list[ModEntry]:
    mods = config["mods"]
    mod_ids = [mod["id"] for mod in mods]
    projects = get_modrinth_projects(session, mod_ids)
    release_order = get_release_game_versions(session)
    entries = []

    for mod in mods:
        mod_id = mod["id"]
        project = projects.get(mod_id)
        name = project.get("title", mod_id) if project else mod_id

        if mod.get("type") == "modrinth":
            versions = latest_modrinth_versions(project, release_order)
            link = f"https://modrinth.com/mod/{quote(mod_id, safe='')}"
        elif mod.get("type") == "github" and mod.get("versionInFileName") and mod.get("repo"):
            versions = get_github_versions(session, mod["repo"], github_token)
            link = f"https://github.com/{quote(mod['repo'], safe='/')}"
        else:
            versions = []
            link = f"https://github.com/{quote(mod.get('repo', ''), safe='/')}" if mod.get("repo") else ""

        entries.append(ModEntry(name=name, url=link, versions=versions))

    return entries


def render_mod_rows(entries: list[ModEntry]) -> str:
    rows = []
    for entry in entries:
        safe_name = html.escape(entry.name)
        if entry.url:
            name_markup = (
                f'<a class="mod-name" href="{html.escape(entry.url, quote=True)}">'
                f"{safe_name}</a>"
            )
        else:
            name_markup = f'<span class="mod-name">{safe_name}</span>'

        if entry.versions:
            version_markup = "".join(
                f'<li class="version">{html.escape(version)}</li>'
                for version in entry.versions
            )
        else:
            version_markup = '<li class="no-versions">暂无版本信息</li>'

        rows.append(
            '<li class="mod-row">'
            f"{name_markup}"
            f'<ul class="versions" aria-label="{safe_name} 支持的最近游戏版本">'
            f"{version_markup}</ul>"
            "</li>"
        )
    return "\n".join(rows)


def render_page(template: str, entries: list[ModEntry], generated_at: datetime | None = None) -> str:
    if generated_at is None:
        generated_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    else:
        generated_at = generated_at.astimezone(ZoneInfo("Asia/Shanghai"))

    update_text = generated_at.strftime("%Y年%m月%d日 %H:%M（UTC+8）")
    return (
        template.replace("{{MOD_ROWS}}", render_mod_rows(entries))
        .replace("{{MOD_COUNT}}", str(len(entries)))
        .replace("{{UPDATED_AT}}", html.escape(update_text))
    )


def generate_site(
    config_path: Path,
    template_path: Path,
    stylesheet_path: Path,
    output_dir: Path,
    *,
    session=None,
    github_token: str | None = None,
    generated_at: datetime | None = None,
) -> list[ModEntry]:
    config = load_config(config_path)
    session = session or create_session()
    entries = collect_mod_entries(config, session, github_token)
    template = template_path.read_text(encoding="utf-8")
    rendered_page = render_page(template, entries, generated_at)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(rendered_page, encoding="utf-8")
    shutil.copyfile(stylesheet_path, output_dir / "style.css")
    return entries


def parse_args():
    parser = argparse.ArgumentParser(description="Generate the DHW Inf mod details site")
    parser.add_argument("--config", type=Path, default=Path("mods.yaml"))
    parser.add_argument("--template", type=Path, default=Path("site/template.html"))
    parser.add_argument("--stylesheet", type=Path, default=Path("site/style.css"))
    parser.add_argument("--output", type=Path, default=Path("_site"))
    return parser.parse_args()


def main():
    args = parse_args()
    entries = generate_site(
        args.config,
        args.template,
        args.stylesheet,
        args.output,
        github_token=os.environ.get("GITHUB_TOKEN"),
    )
    print(f"Generated {len(entries)} mod entries in {args.output}")


if __name__ == "__main__":
    main()
