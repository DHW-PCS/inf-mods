# DHW Inf 服务器模组下载器  
**DHW Inf Server Mod Downloader**  

---

### 1. 程序说明 / Program Description  
该工具由 DHW 开度署 (Development Agency of DHW) 维护，用于自动化管理 DHW Inf Minecraft 服务器（“本服”）的模组。玩家或贡献者只需修改 `mods.yaml` 配置文件并提交 Pull Request，即可申请将新模组添加到本服中。  
This tool is maintained by the Development Agency of DHW (开度署) to automate mod management for the DHW Inf Minecraft server (*Server*). Players and contributors can add new mods by modifying the `mods.yaml` file and submitting a Pull Request.  

---

### 2. 模组提交要求 / Mod Submission Requirements  
- **发布平台**: 必须已在 **Modrinth** 或 **GitHub Releases** 公开发布。  
  **Platform**: Must be publicly released on **Modrinth** or **GitHub Releases**.  
- **类型限制**: 禁止提交**要求客户端安装**的模组（只能提交纯服务端模组或客户端可选模组）。  
  **Restriction**: Client-side mandatory mods are prohibited (server-only or client-optional mods only).  
- **开度署保留是否将模组加入到本服的最终决定权**
- **Development Agency reserves the final say on whether mods are added to *Server*.** 

---

### 3. 配置示例 / Configuration Examples  
#### Modrinth 模组 (示例: `fabric-api`)  
```yaml
mods:
- id: fabric-api  # Modrinth 项目 ID (从URL获取: modrinth.com/mod/fabric-api)
  type: modrinth # 表示该模组在 Modrinth 上发布
```  
> 一般情况下，若要提交 Modrinth 上发布的模组，只需提供 `id` 和 `type`。  

#### GitHub 模组 (示例: `pca-protocol`)  
```yaml
mods:
- id: pca-protocol  # 自定义标识，尽量与模组开发者采用的名称一致
  type: github # 表示该模组在 GitHub 上发布
  repo: Fallen-Breath/pca-protocol  # GitHub 仓库路径
  versionInFileName: true  # 文件名需包含 Minecraft 版本号 (如: pca-protocol-v0.3.9-mc1.21.8.jar)
```  
> 若文件名**不包含版本号**，需改用 `releaseFilter` 匹配发布名称，例如:  
> ```yaml
> releaseFilter: "1.21.7"  # 筛选发布名称中包含该字符串的版本
> ```  
> (这部分内容还是💩，以后有机会再改进，~~反正能跑就行~~)

---

### 4. 作为 Python 模块使用 / Python Module API

`download.py` 可以直接导入；导入时不会读取配置、创建目录、访问网络或输出信息。批量下载会按配置顺序返回一个 `DownloadResult` 列表，单个模组失败不会中止其余下载。

使用已解析的配置字典：

```python
from download import download_mods

config = {
    "mcVersion": "1.21.11",
    "modLoader": "fabric",
    "mods": [
        {"id": "fabric-api", "type": "modrinth"},
    ],
}

results = download_mods(config, output_dir="server-mods")
for result in results:
    if result.success:
        print(result.mod_id, result.target_path)
    else:
        print(result.mod_id, result.error or "No matching file")
```

从 YAML 文件加载并下载：

```python
from download import download_from_file

results = download_from_file("mods.yaml", output_dir="server-mods")
```

如果只需读取 YAML，可单独调用 `load_config("mods.yaml")` 获取配置字典。

`download_mod()` 可处理单个配置项。所有网络相关函数均接受可选的 `session` 参数，调用方可以传入 `requests.Session()` 以复用连接或进行测试。

服务器升级流程应显式传入目标 Minecraft 版本，并先下载到独立暂存目录：

```python
from download import download_mods_for_version, load_config

config = load_config("mods.yaml")
batch = download_mods_for_version(
    config,
    "1.21.12",
    output_dir="staging/mods",
)
batch.raise_for_failures()
```

这个入口不会修改 `config`，也不会自动沿用其中面向旧服务器版本的 `mcCompatibles`。如果已确认某个旧版模组兼容新版，必须显式提供回退版本：

```python
batch = download_mods_for_version(
    config,
    "1.21.12",
    output_dir="staging/mods",
    compatible_versions=["1.21.11"],
)
```

异步升级工作流可使用非阻塞包装：

```python
from download import async_download_mods_for_version

batch = await async_download_mods_for_version(
    config,
    "1.21.12",
    output_dir="staging/mods",
)
batch.raise_for_failures()
```

`DownloadBatchResult.success` 表示整个批次是否成功，`failures` 包含全部失败项，`as_dict()` 可直接交给 `json.dumps()`。`raise_for_failures()` 抛出的 `DownloadBatchError` 会通过其 `result` 属性保留完整批次，便于升级程序输出诊断后安全中止。

直接执行 `python download.py` 时，程序仍会读取当前目录下的 `mods.yaml` 并将文件下载到 `mods/`。

---

### 5. 模组详情页面 / Mod Details Page

仓库包含一个由 `mods.yaml` 生成的静态模组详情页面。页面展示从 Modrinth 获取的模组名称，以及各模组最近支持的三个正式 Minecraft 版本；GitHub 模组的版本会按 `versionInFileName` 配置从 Release 的 JAR 文件名中提取。

本地生成页面：

```bash
python3 -m pip install -r requirements.txt
python3 generate_site.py
```

生成结果位于 `_site/`。页面显示的“数据更新”时间采用 UTC+8。

GitHub Actions 会在以下情况重新生成并部署页面：

- 推送到 `main` 分支；
- 从 Actions 页面手动运行；
- 每天 03:17 UTC 自动运行。

页面地址为：<https://dhw-pcs.github.io/inf-mods/>
