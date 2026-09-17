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

Carpet/Extra 从标题中的 Minecraft 版本识别兼容性，支持明确范围（例如 `1.21.9-1.21.11`）；AMS/TIS 从文件名中的 `mc` 版本识别。范围和 `.x` 通配符以 [Mojang 官方 manifest](https://piston-meta.mojang.com/mc/game/version_manifest_v2.json) 中的 `release` 版本为准；范围按 `releaseTime` 排序后包含两端，支持跨版本，通配符仅匹配已发布的对应系列。端点不存在、范围反向或 manifest 获取/解析失败时停止生成，不推算不存在的版本。快照版本不会作为对应正式版本展示。维护工具需同时更新；目录变更推送到 `DHW-PCS/inf-mods` 的 `main` 后才会被维护工具获取。

All four Carpet mods use GitHub Releases. Carpet/Extra use Minecraft versions in release titles, including explicit ranges; AMS/TIS use the `mc` version in asset names. Ranges and `.x` wildcards use actual `release` entries from the Mojang manifest. Ranges include both endpoints in `releaseTime` order, including across minor/major versions; wildcards select published members of the named series. Missing endpoints, reversed ranges, and manifest errors stop generation without inventing versions. Snapshot versions are not displayed as stable versions. Update the maintenance tools alongside this catalogue; they consume catalogue changes after publication to `DHW-PCS/inf-mods` `main`.

## 模组详情页面 / Mod Details Site

页面展示 Modrinth 模组名称及最近支持的三个正式 Minecraft 版本；GitHub 模组版本按目录配置从 Release JAR 文件名或 Release 标题提取。

The site shows Modrinth project names and their three latest supported release versions. GitHub versions are extracted from Release JAR filenames or release titles according to the catalogue configuration.

本地生成：

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 generate_site.py
```

测试按职责划分：`test_mod_metadata.py` 验证版本选择、manifest 和 HTTP 错误处理；`test_generate_site.py` 验证目录接线、生成文件及 HTML 转义。HTTP 替身集中在 `tests/support.py`，不重复测试导入别名或固定样式/文案。

生成结果位于 `_site/`，页面中的更新时间采用 UTC+8。GitHub Actions 会在推送到 `main`、手动运行以及每天 03:17 UTC 时重新测试、生成并部署页面。

Generated files are written to `_site/`, and the displayed update time uses UTC+8. GitHub Actions tests, rebuilds, and deploys the site on pushes to `main`, manual runs, and daily at 03:17 UTC.

页面地址：<https://dhw-pcs.github.io/inf-mods/>
