# DHW Inf 模组目录

**DHW Inf Mod Catalogue**

本仓库保存 DHW Inf Minecraft 服务器使用的模组目录，并由 `mods.yaml` 生成公开的模组详情页面。模组的选择、下载、校验和部署由 [`inf-maintenance-tools`](https://github.com/DHW-PCS/inf-maintenance-tools) 负责；本仓库不再提供独立下载器或 Python 下载 API。

This repository contains the mod catalogue for the DHW Inf Minecraft server and generates its public mod-details site from `mods.yaml`. Mod selection, download, verification, and deployment are owned by [`inf-maintenance-tools`](https://github.com/DHW-PCS/inf-maintenance-tools); this repository no longer provides a standalone downloader or Python download API.

## 提交模组 / Proposing Mods

玩家或贡献者可修改 `mods.yaml` 并提交 Pull Request。模组必须已在 Modrinth 或 GitHub Releases 公开发布，且只能是纯服务端模组或客户端可选模组；要求客户端强制安装的模组不予接受。DHW 开度署保留是否加入模组的最终决定权。

Players and contributors may edit `mods.yaml` and submit a pull request. Mods must be publicly released on Modrinth or GitHub Releases and must be server-only or client-optional. Mods that require every client to install them are not accepted. The Development Agency of DHW retains the final decision.

### Modrinth

```yaml
mods:
- id: fabric-api
  type: modrinth
```

`id` 使用 Modrinth 项目 ID。通常只需提供 `id` 和 `type`。

Use the Modrinth project ID for `id`. Normally only `id` and `type` are required.

### GitHub Releases

```yaml
mods:
- id: pca-protocol
  type: github
  repo: Fallen-Breath/pca-protocol
  versionInFileName: true
```

`repo` 必须是完整的 `owner/repository`。当发布文件名包含 Minecraft 版本号时使用 `versionInFileName`；也可使用 `versionInRelease` 按 Release 名称匹配版本，或用 `releaseFilter`、`versionFilter` 提供明确的字符串过滤条件。

`repo` must be a complete `owner/repository` path. Use `versionInFileName` when release filenames contain the Minecraft version. `versionInRelease` matches versions in release names, while `releaseFilter` and `versionFilter` provide explicit string filters.

Carpet 系四个模组统一使用 GitHub Releases：

| 模组 / Mod | GitHub repository | 版本识别 / Version selection |
| --- | --- | --- |
| Carpet | `gnembon/fabric-carpet` | `versionInRelease` |
| Carpet AMS Addition | `Minecraft-AMS/Carpet-AMS-Addition` | `versionInFileName` |
| Carpet Extra | `gnembon/carpet-extra` | `versionInRelease` |
| Carpet TIS Addition | `TISUnion/Carpet-TIS-Addition` | `versionInFileName` |

Carpet/Extra 从标题中的 Minecraft 版本识别兼容性，支持明确范围（例如 `26.1.2-26.3`）；AMS/TIS 从文件名中的 `mc` 版本识别。

兼容性判断对 GitHub 与 Modrinth 一致，且一律以 [Mojang 官方 manifest](https://piston-meta.mojang.com/mc/game/version_manifest_v2.json) 中的 `release` 列表为准：声明里的版本号只用来在 manifest 中**查找真实正式版**，之后的判断全部是对这些真实版本的集合运算，不做数字或字符串比较，次序也按 manifest 的 `releaseTime` 而非版本号大小。

- **同一系列默认向后兼容**。系列按前两段划分：`26.1`、`26.1.1`、`26.1.2` 同属 26.1 系列。声明的两段版本（如 `26.1`）是系列头，覆盖该系列全部正式版；声明的三段及以上版本（如 `26.1.2`）覆盖其自身及同系列更晚版本，但**不回溯**更早的 `26.1`、`26.1.1` —— 对它们的支持由「`26.1`」这个声明提供。
- **显式范围是精确集合**，不参与向后默认：`26.1.2-26.3` 就只含 `26.1.2`、`26.2`、`26.3`。按 `releaseTime` 排序后包含两端，支持跨版本。
- **`.x` 通配符**（如 `26.1.x`）等同该系列头，匹配已发布的对应系列。

快照与预发布（如 `26.3-pre-1`、`26.4-snapshot-1`）不参与判断，也不会作为对应正式版本展示。不存在的系列或不存在的补丁版本不贡献任何版本，不推算。范围端点不存在、范围反向或 manifest 获取/解析失败时停止生成。维护工具需同时更新；目录变更推送到 `DHW-PCS/inf-mods` 的 `main` 后才会被维护工具获取。

All four Carpet mods use GitHub Releases. Carpet/Extra use Minecraft versions in release titles, including explicit ranges; AMS/TIS use the `mc` version in asset names.

Compatibility works the same way for GitHub and Modrinth, and always defers to the `release` list in the [Mojang manifest](https://piston-meta.mojang.com/mc/game/version_manifest_v2.json): a declared version number is only ever used to **look up real releases**, and every decision afterwards is a set operation over those releases. Nothing compares numbers or strings, and ordering comes from `releaseTime` rather than from version magnitude.

- **One series is compatible by default, going forward.** A series is the first two parts, so `26.1`, `26.1.1` and `26.1.2` share the 26.1 series. A declared two-part version (such as `26.1`) is the series head and covers the whole series. A declared three-part-or-longer version (such as `26.1.2`) covers itself and the later releases of its series, but never goes back to `26.1` or `26.1.1` — support for those comes from the `26.1` declaration.
- **An explicit range is an exact set** and never takes the series default: `26.1.2-26.3` means `26.1.2`, `26.2` and `26.3` and nothing else. Ranges include both endpoints in `releaseTime` order, including across minor/major versions.
- **An `.x` wildcard** (such as `26.1.x`) is the series head by another name and selects published members of that series.

Snapshots and pre-releases (such as `26.3-pre-1`, `26.4-snapshot-1`) take no part in the judgement and are never displayed as stable versions. A series that does not exist, or a patch version that does not exist, claims nothing; nothing is inferred. Missing range endpoints, reversed ranges, and manifest errors stop generation. Update the maintenance tools alongside this catalogue; they consume catalogue changes after publication to `DHW-PCS/inf-mods` `main`.

## 模组详情页面 / Mod Details Site

页面展示模组名称及其支持的最新三个正式 Minecraft 版本：先把声明版本按上述规则展开成真实正式版，再取其中最新的三个。顶部同时给出最新三个正式版的模组兼容比例。GitHub 模组的声明版本按目录配置从 Release JAR 文件名或 Release 标题读取。

The site shows each mod's three newest supported release versions, expanded into real releases by the rules above, along with the share of the catalogue behind each of the three newest releases. GitHub declarations are read from Release JAR filenames or release titles according to the catalogue configuration.

本地生成：

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 generate_site.py
```

测试按职责划分：`test_mod_metadata.py` 验证系列展开规则、manifest 校验和 HTTP 错误处理；`test_generate_site.py` 使用独立的测试数据验证生成文件及 HTML 转义。HTTP 替身集中在 `tests/support.py`；测试不读取实际的 `mods.yaml`，不固定模组数量、选择或顺序，也不固定样式/文案。

Tests use isolated fixtures rather than the live `mods.yaml`, so adding, removing, or reordering catalogue entries does not require test changes.

生成结果位于 `_site/`，页面中的更新时间采用 UTC+8。GitHub Actions 会在推送到 `main`、手动运行以及每天 03:17 UTC 时重新测试、生成并部署页面。

Generated files are written to `_site/`, and the displayed update time uses UTC+8. GitHub Actions tests, rebuilds, and deploys the site on pushes to `main`, manual runs, and daily at 03:17 UTC.

页面地址：<https://dhw-pcs.github.io/inf-mods/>
