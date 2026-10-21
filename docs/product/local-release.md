# 本地源码包与使用指南

适用 Windows x64、Python 3.11。当前版本号来自 `pyproject.toml`。本地发行物是包含 Python 源码和已构建网页的 ZIP，**不是免安装 EXE**。正常使用这个 ZIP 不需要 Node、Docker、WSL 或数据库；从源码重新构建网页才需要项目内 Node 依赖。

## 安装、启动与停止

将程序 ZIP 解压到可写的新目录，避免系统目录、网盘同步目录及同一个工作区的多个副本同时运行。先安装 Python 3.11 x64，然后在解压目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-local.ps1
```

可用 `-PythonExe D:\Python311\python.exe` 指定解释器。安装只写项目 `.venv` 和本地缓存，不改全局 Python、注册表、系统环境变量或 PowerShell 执行策略。首次安装默认联网下载依赖；发布包中的 `requirements-release.txt` 固定构建机验证过的依赖版本。若准备了完整且兼容的 wheels（包括构建工具），可用 `-Offline -Wheelhouse D:\wheels` 离线安装。程序包不附带 Python、wheels 或可选 AI 权重。

安装后双击 `Start-Workspace.cmd`，浏览器访问 `http://127.0.0.1:8510`。启动窗口保持打开，按 Ctrl+C 停止。也可运行 `scripts\start-local.ps1 -Port 8511` 更换端口。仅启动一个服务进程操作同一工作区；目前编辑锁在进程内，不能协调多个后端进程或与 Streamlit 同时写入。窗口和浏览器不会自动隐藏，方便查看故障信息。

```powershell
# 只检查环境与依赖，不安装或下载
powershell -ExecutionPolicy Bypass -File scripts\install-local.ps1 -CheckOnly
# 生成本地诊断 JSON，不上传
powershell -ExecutionPolicy Bypass -File scripts\diagnose-local.ps1
```

诊断输出位于 `.cache/diagnostics/`，包含版本、依赖状态、端口占用与目录存在性；不写密钥值、图片、项目名称或本机完整路径。报错时先运行诊断并检查磁盘空间。程序安装、端口或依赖失败不会删除个人数据。

## 创作与提取

在项目库上传图片，打开工作台后按需提取、画笔修正、重组、配色、保存与导出。原图保留在项目 `source/` 中，结果另存版本。确认提取变化可能使依赖它的后续成果过期；历史成果仍需通过版本与导出记录核对来源。

提取模式按素材选择：

| 模式 | 适用场景与限制 |
| --- | --- |
| 自动 | 已有透明通道时保留原透明像素；鲜明单色剪纸优先按色相提取，否则用 OpenCV。仍需检查背景误选。 |
| OpenCV | 明暗或颜色较清楚的纹样；器物照片配置需要先框选主体。 |
| 选色 | 通过颜色选择器选定颜色，调节 Lab 颜色容差 1–100；背景同色会一并选中。 |
| 保留整图 | 已处理透明 PNG、或希望直接使用整张画面的素材；保留每个原透明度值和细小像素。 |
| MobileSAM | 本机安装依赖与校验通过的权重后可选；在编辑器中先框选主体，首次 CPU 加载较慢。不会自动下载安装。 |

选色坐标、选区与笔触均以方向已校正的工作图像素为准。小区域过滤、填孔、平滑先于手动画笔运行，画笔修正在最后应用。填孔会封闭剪纸镂空，平滑可能损失细线，默认关闭。柔化只作用于 RGBA 边缘，分析蒙版仍为二值；任何模式都不能恢复源图本已透明的像素。复杂纹理、细线、镂空、同色背景都需要目视检查，算法返回成功不等于已完成精修。

导入、提取、重组、配色、文创与常规导出在依赖安装后可离线运行。AI 生图需要用户主动触发远程供应商请求，会使用网络并可能计费；密钥应通过本机配置或会话输入，不放进项目、程序发行包或截图。可选 MobileSAM 是本地处理，与远程 AI 生图是不同功能。

## 备份、恢复与升级

三种 ZIP 用途不同：程序源码包安装应用；项目备份包用于项目迁移与恢复；作品导出包用于交付图像和来源说明，不能代替完整项目备份。使用工作台提供的项目备份/导入功能时，应检查原图、版本及项目记录是否一并恢复。恢复到新项目后先核对预览，再继续编辑。

完整本机备份：停止服务，复制整个 `workspace/`、`outputs/`、`models/`、`config/` 及私有 `.env`、`.streamlit/secrets.toml` 到自己的安全目录。备份中的密钥文件和私有素材同样敏感，不随问题反馈公开。若设置 `PATTERN_REBORN_WORKSPACE` 或 `PATTERN_REBORN_OUTPUTS` 指向外部目录，也要单独备份这些目录。诊断和升级脚本不读取环境变量中的密钥值。

升级使用新目录，保留旧目录作回退：

```powershell
# 先停止旧服务；目标目录必须尚不存在，父目录需已存在
powershell -ExecutionPolicy Bypass -File scripts\upgrade-local.ps1 `
  -ArchivePath D:\Downloads\pattern-reborn-VERSION-local-TIME.zip `
  -Destination D:\Apps\pattern-reborn-new
```

脚本在写入前检查程序包格式、路径、重复条目及 manifest 中的文件校验值；校验可检测损坏，不能验证发布者身份。只使用可信来源的程序 ZIP。校验后解压到新目录，再复制旧目录的项目、成果、模型、配置和私有配置文件，不删除旧数据、不自动安装或启动。目录联接/符号链接不会自动跟随复制；外部工作区目录请独立备份并配置。复制中途失败时新目录可能不完整，旧目录保持原样。

进入新目录运行安装脚本、环境检查，再启动核对项目和导出。确认前保留旧程序及备份。回退时停止新服务，重新启动旧目录；升级后新建或编辑的数据不会自动同步回旧目录，请先另行备份。卸载时停止服务并移走个人数据，再自行删除程序目录；无系统服务需要注销。

## 制作本地发行物

开发者在测试通过、网页重新构建后运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\release-local.ps1
# 如需重建，使用已有的项目 Node 依赖
powershell -ExecutionPolicy Bypass -File scripts\release-local.ps1 -Build -NodeExecutable D:\runtime\node.exe
```

输出到忽略的 `dist/local/`。ZIP 有唯一版本名、前端成品、源码、使用说明、文件 SHA-256 manifest、依赖版本与许可证文本，旁边附 ZIP SHA-256 文件。包中不含 `.venv`、缓存、用户工作区、成果、模型权重、私有 `.env` 或未提交补丁；Node/Python 依赖二进制也不随包提供。制作脚本不发布到 GitHub、Vercel 或其他服务。

仓库当前没有项目自身的 `LICENSE`，第三方声明不等于项目授权。本地程序包仅用于已有授权范围内的使用；公开再分发前需由权利人明确项目许可，并核对示例素材、字体、图标和其他第三方许可证。发行包的 `licenses/` 保存构建环境可取得的许可证原文，示例素材归属见 `THIRD_PARTY_NOTICES.md` 与 `data/demo/` 的元信息。

## 本轮验证范围

2026-10-21 在 Windows、Python 3.11.9 x64 验证脚本语法、现有 `.venv` 依赖检查与诊断；实际生成程序 ZIP、核对全部文件校验值、验证私有文件排除及许可证文本。在新的临时程序目录中启动真实后端与前端，并验证升级复制工作区、成果、模型和私有配置、保留旧目录。临时程序沿用了本机已安装的 Python 依赖；尚未在全新 Windows 系统上重新联网安装全部依赖，不据此承诺免环境安装。

自动测试覆盖取色/笔触边界、透明度、清理后画笔优先、ZIP 路径与 manifest 校验。固定随机种子的“灰色纹理背景 + 红色剪纸 + 镂空”合成图，OpenCV 基线 IoU 为 0.113，自动和选色为 1.0；这只说明此回归样本通过，不代表任意实拍图片的质量。真实复杂照片仍需人工验收。
