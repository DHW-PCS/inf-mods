import argparse
import html
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import yaml

from mod_metadata import (
    ReleaseCatalogue,
    create_session,
    get_github_versions,
    get_modrinth_projects,
    load_release_catalogue,
    modrinth_supported_versions,
)


DISPLAY_VERSIONS = 3


@dataclass(frozen=True)
class ModEntry:
    name: str
    url: str
    versions: list[str]


@dataclass(frozen=True)
class VersionReadiness:
    """How much of the catalogue is on board for one Minecraft release."""

    version: str
    supported: int
    total: int

    @property
    def percent(self) -> int:
        if not self.total:
            return 0
        return round(self.supported / self.total * 100)


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    if not isinstance(config, dict) or not isinstance(config.get("mods"), list):
        raise ValueError("mods.yaml must contain a mods list")
    return config


def collect_mod_entries(
    config: dict,
    session,
    catalogue: ReleaseCatalogue,
    github_token: str | None = None,
) -> list[ModEntry]:
    mods = config["mods"]
    mod_ids = [mod["id"] for mod in mods]
    projects = get_modrinth_projects(session, mod_ids)
    entries = []

    for mod in mods:
        mod_id = mod["id"]
        project = projects.get(mod_id)
        name = project.get("title", mod_id) if project else mod_id

        if mod.get("type") == "modrinth":
            versions = modrinth_supported_versions(project, catalogue)
            link = f"https://modrinth.com/mod/{quote(mod_id, safe='')}"
        elif (
            mod.get("type") == "github"
            and (mod.get("versionInFileName") or mod.get("versionInRelease"))
            and mod.get("repo")
        ):
            versions = get_github_versions(
                session,
                mod["repo"],
                catalogue,
                github_token,
                version_in_release=bool(mod.get("versionInRelease")),
            )
            link = f"https://github.com/{quote(mod['repo'], safe='/')}"
        else:
            versions = []
            link = (
                f"https://github.com/{quote(mod.get('repo', ''), safe='/')}"
                if mod.get("repo")
                else ""
            )

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
            # Only the rows are capped; the readiness band reads the full list.
            latest, *earlier = entry.versions[:DISPLAY_VERSIONS]
            version_items = [
                '<li class="v v--latest">'
                '<span class="visually-hidden">最新支持版本 </span>'
                f"{html.escape(latest)}</li>"
            ]
            version_items.extend(
                f'<li class="v">{html.escape(version)}</li>' for version in earlier
            )
            versions_markup = (
                f'<ul class="versions" aria-label="{safe_name} 支持的正式版本">'
                f'{"".join(version_items)}</ul>'
            )
        else:
            versions_markup = '<p class="v-empty">暂无版本信息</p>'

        rows.append(
            '<li class="mod-row">'
            f"{name_markup}"
            f"{versions_markup}"
            "</li>"
        )
    return "\n".join(rows)


def collect_readiness(
    releases: list[str],
    entries: list[ModEntry],
    limit: int = 3,
) -> list[VersionReadiness]:
    """The newest releases first, each with the share of the catalogue behind it."""
    newest_first = list(reversed(releases))[:limit]
    claimed = [set(entry.versions) for entry in entries]
    return [
        VersionReadiness(
            version=version,
            supported=sum(1 for versions in claimed if version in versions),
            total=len(entries),
        )
        for version in newest_first
    ]


def render_readiness(readiness: list[VersionReadiness]) -> str:
    cells = []
    for item in readiness:
        cells.append(
            '<li class="readiness__item">'
            f'<span class="readiness__version">{html.escape(item.version)}</span>'
            f'<span class="readiness__ratio" style="--readiness: {item.percent}">'
            '<span class="visually-hidden">模组兼容 </span>'
            f"{item.percent}%</span>"
            "</li>"
        )
    return "\n".join(cells)


def render_page(
    template: str,
    entries: list[ModEntry],
    generated_at: datetime | None = None,
    readiness: list[VersionReadiness] | None = None,
) -> str:
    if generated_at is None:
        generated_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    else:
        generated_at = generated_at.astimezone(ZoneInfo("Asia/Shanghai"))

    update_text = generated_at.strftime("%Y年%m月%d日 %H:%M（UTC+8）")
    return (
        template.replace("{{READINESS}}", render_readiness(readiness or []))
        .replace("{{MOD_ROWS}}", render_mod_rows(entries))
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
    # Fetched once and shared: every entry resolves its declarations against it,
    # and the readiness band needs the same release list.
    catalogue = load_release_catalogue(session)
    entries = collect_mod_entries(config, session, catalogue, github_token)
    readiness = collect_readiness(catalogue.versions, entries)
    template = template_path.read_text(encoding="utf-8")
    rendered_page = render_page(template, entries, generated_at, readiness)

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
