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

## 模组详情页面 / Mod Details Site

页面展示 Modrinth 模组名称及最近支持的三个正式 Minecraft 版本；GitHub 模组版本按目录配置从 Release JAR 文件名提取。

The site shows Modrinth project names and their three latest supported release versions. GitHub versions are extracted from Release JAR filenames according to the catalogue configuration.

本地生成：

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 generate_site.py
```

生成结果位于 `_site/`，页面中的更新时间采用 UTC+8。GitHub Actions 会在推送到 `main`、手动运行以及每天 03:17 UTC 时重新测试、生成并部署页面。

Generated files are written to `_site/`, and the displayed update time uses UTC+8. GitHub Actions tests, rebuilds, and deploys the site on pushes to `main`, manual runs, and daily at 03:17 UTC.

页面地址：<https://dhw-pcs.github.io/inf-mods/>
