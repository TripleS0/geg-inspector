# DataFusionX

DataFusionX 是一个离线运行的数据整合与分析桌面应用。当前项目已收敛为标准前后端架构：后端使用 FastAPI，前端使用 React，桌面壳使用 Tauri。旧的 PySide6 桌面方案不再作为开发、运行或交付路径。

## 功能概览

- 银行流水导入、模板录入、字段映射、标准化、查询分析与导出。
- 商务网数据导入、商务网分析、商务网风险规则识别、统计报告导出。
- 工商信息录入与商务企业匹配。
- 数据脱敏、批次管理、数据表预览与清理。
- 本地 SQLite 持久化，离线运行，不依赖外部数据库服务。

## 技术栈

- Backend：Python 3.10+、FastAPI、SQLite、pandas、openpyxl。
- Frontend：React、TypeScript、Ant Design、ECharts、Vite。
- Desktop：Tauri 1.x、Rust、PyInstaller 打包的本地 FastAPI 后端。

## 项目结构

```text
DataFusionX/
├── backend/
│   ├── main.py                 # FastAPI 应用入口
│   ├── entry.py                # PyInstaller 后端 exe 入口
│   ├── app/
│   │   ├── application/        # 用例层
│   │   ├── services/           # 业务服务层
│   │   ├── resources/          # SQL、配置示例等后端资源
│   │   └── runtime_paths.py    # 本地数据/导出/上传目录策略
│   └── tests/                  # 后端测试
├── frontend/
│   ├── src/                    # React 页面、API client、主题
│   ├── package.json
│   └── vite.config.ts
├── src-tauri/
│   ├── src/main.rs             # 桌面壳，负责拉起 backend.exe
│   ├── Cargo.toml
│   └── tauri.conf.json
├── scripts/
│   ├── build_backend.py        # 构建 backend-dist/backend.exe
│   └── build_desktop.ps1       # 构建前端、后端与 Tauri 安装包
├── legacy/pyside6/             # 旧 PySide6 代码，仅保留历史参考
├── data/                       # 本地运行数据，Git 忽略
├── exports/                    # 导出文件，Git 忽略
├── requirements.txt
└── README.md
```

## 开发运行

### 1. 安装后端依赖

```bash
pip install -r requirements.txt
```

### 2. 启动 FastAPI 后端

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

后端默认会在项目根目录创建并使用：

- 数据库：`data/datafusionx.sqlite3`
- 上传缓存：`data/uploads/`
- 导出目录：`exports/`

### 3. 启动 React 前端

```bash
cd frontend
npm install
npm run dev
```

开发期访问 `http://127.0.0.1:5173`。前端默认通过 Vite 代理访问 `http://127.0.0.1:8765/api`。

## 桌面版开发联调

需要先安装 Rust 与 Tauri CLI：

```bash
cargo install tauri-cli --version "^1.6"
```

联调桌面壳：

```bash
cargo tauri dev --manifest-path src-tauri/Cargo.toml
```

开发联调时，Tauri 会启动前端 dev server；生产打包时，Tauri 会加载 `frontend/dist` 并拉起内置 `backend.exe`。

## 打包本地桌面版

### 方式 A：一键脚本

```powershell
.\scripts\build_desktop.ps1
```

脚本会按顺序执行：

1. `npm --prefix frontend install`
2. `npm --prefix frontend run build`
3. `python scripts/build_backend.py`
4. `cargo tauri build --manifest-path src-tauri/Cargo.toml`

安装包输出位置：

```text
src-tauri/target/release/bundle/
```

**C: 空间不足**：可将 Rust 的 `CARGO_HOME`、`RUSTUP_HOME` 与用户 `TEMP/TMP` 指到 D:（默认 `D:\GDNY_tuomi\rust-on-d`），并可选复制原 `%USERPROFILE%\.cargo`、`.rustup`：

```powershell
.\scripts\setup_rust_on_d.ps1 -CopyFromDefaultProfile -SetUserTemp
```

执行后**完全退出 Cursor 与所有终端**再打开，然后 `cargo --version`；再在空间充足的盘上执行 `cargo install tauri-cli`。

### 方式 B：分步构建

```bash
cd frontend
npm install
npm run build
cd ..

python scripts/build_backend.py
cargo tauri build --manifest-path src-tauri/Cargo.toml
```

`scripts/build_backend.py` 会把后端打包为：

```text
backend-dist/backend.exe
```

Tauri 打包时会将 `frontend/dist` 与 `backend-dist` 一起嵌入安装包。

## 本地数据库与历史数据

SQLite 是本地文件数据库，不需要安装数据库服务。为避免升级或重新打包导致历史数据丢失，运行目录策略如下：

- 浏览器开发模式：默认使用项目根目录下的 `data/datafusionx.sqlite3`。
- Tauri 桌面模式：桌面壳启动后端时会传入 `DATAFUSIONX_HOME`，后端会把数据库、上传缓存和导出目录写入稳定的本地应用数据目录。未手动设置时，Windows 上通常为 `%LOCALAPPDATA%\com.datafusionx.desktop\runtime`（其下仍有 `data/`、`exports/`、`logs/` 等，与开发模式结构一致）。
- 手动覆盖整个运行数据根目录：

```powershell
$env:DATAFUSIONX_HOME="D:\DataFusionXRuntime"
```

- 手动覆盖单独数据库文件：

```powershell
$env:DATAFUSIONX_DB_PATH="D:\DataFusionXRuntime\datafusionx.sqlite3"
```

优先级：

1. `DATAFUSIONX_DB_PATH`
2. `DATAFUSIONX_HOME\data\datafusionx.sqlite3`
3. 开发模式默认 `data/datafusionx.sqlite3`

备份建议：

- 定期备份 `datafusionx.sqlite3`。
- 迁移电脑时，复制完整运行数据目录，至少包含 `data/datafusionx.sqlite3` 与需要保留的 `exports/`。
- 不要把 `data/`、`exports/`、`logs/` 提交到 Git；这些目录已在 `.gitignore` 中忽略。

## 企查查配置

可通过环境变量配置：

```powershell
$env:QICHACHA_APP_KEY="你的 AppKey"
$env:QICHACHA_SECRET_KEY="你的 SecretKey"
```

也可在本地运行数据目录放置：

```text
data/qichacha_config.json
```

格式参考：

```text
backend/app/resources/config/qichacha_config.example.json
```

不要提交包含真实密钥的配置文件。

## 验证命令

后端测试：

```bash
python -m unittest discover -s backend/tests -t backend
```

前端构建：

```bash
npm --prefix frontend run build
```

后端打包：

```bash
python scripts/build_backend.py
```

## 旧 PySide6 代码

`legacy/pyside6/` 仅用于保留历史代码参考，不参与当前依赖安装、开发运行或桌面打包。新的桌面版只维护 FastAPI + React + Tauri 路线。
