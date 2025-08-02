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