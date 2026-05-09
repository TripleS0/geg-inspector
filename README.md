# DataFusionX

DataFusionX 是一个面向企业数据整合场景的离线桌面工具。当前版本提供可扩展工具平台壳层，并已接入本地 SQLite 的多来源整合流程（多 sheet 导入、模板识别、原始层入库、全字段合并导出）。

## 当前功能

- 平台化主界面（左侧导航 + 右侧页面区）
- 分组导航菜单与页面切换（Router 解耦）
- 首页展示（项目名、Logo、简介、快捷入口卡片）
- 数据上传页（选择文件、选择文件夹递归读取、清空列表、拖拽导入、查看数据预览）
- 数据脱敏模块（沿用历史工具能力，支持 txt/xlsx/xls）
- 数据整合流程（自动初始化数据库、批量入库；银行入口可标准化，商务网入口跳过银行标准化）
- 全字段合并导出（`.xlsx`，银行/商务网均为单工作表 `全字段合并`，首列为“数据来源”）

## 技术栈

- Python 3.10+
- PySide6
- QSS 样式系统
- 类型注解（typing）与 docstring
- SQLite（本地文件数据库）

## 运行方式

```bash
pip install -r requirements.txt
python main.py
```

## 项目结构说明

```text
project_root/
│
├── main.py
├── app/
│   ├── main_window.py
│   ├── navigation.py
│   ├── router.py
│   │
│   ├── pages/
│   │   ├── home_page.py
│   │   ├── desensitization_page.py
│   │   ├── integration_select_page.py
│   │   ├── upload_page.py
│   │   ├── process_page.py
│   │   └── export_page.py
│   │
│   ├── widgets/
│   │   ├── file_list_widget.py
│   │   ├── log_widget.py
│   │   └── card_button.py
│   │
│   ├── services/
│   │   ├── desensitization/
│   │   │   └── desensitizer_service.py
│   │   ├── integration/
│   │   │   ├── factory.py
│   │   │   ├── bank/
│   │   │   │   ├── ingest_service.py
│   │   │   │   ├── mapping_service.py
│   │   │   │   └── export_service.py
│   │   │   ├── commercial/
│   │   │   │   ├── ingest_service.py
│   │   │   │   ├── mapping_service.py
│   │   │   │   └── export_service.py
│   │   │   └── common/
│   │   │       └── bootstrap.py
│   │   └── shared/
│   │       └── db/
│   │           └── sqlite_client.py
│   │
│   └── resources/
│       ├── styles.qss
│       ├── icons/
│       ├── config/db.example.json
│       └── sql/bootstrap_sqlite.sql
│
├── requirements.txt
├── version.txt
├── README.md
└── .gitignore
```

- `main.py`：应用入口，负责启动 `QApplication`、加载全局 QSS、设置窗口图标并创建主窗口。
- `app/main_window.py`：主窗口壳层，组合左侧导航与右侧页面容器，管理路由注册和页面切换。
- `app/navigation.py`：左侧导航组件，负责菜单分组渲染、选中高亮、品牌区（logo+标题）显示与路由信号发射。
- `app/router.py`：页面路由中心，封装 `QStackedWidget` 的注册、别名映射和切换逻辑，降低页面耦合。

- `app/pages/`：业务页面层，每个文件一个页面类，便于独立扩展。
- `app/pages/home_page.py`：工具平台首页，展示品牌信息与工具入口卡片（数据整合/数据脱敏/其他）。
- `app/pages/integration_select_page.py`：数据整合来源选择页，提供商务网/银行/其他数据入口选择。
- `app/pages/upload_page.py`：上传页（可用），支持文件选择、文件夹递归读取、拖拽导入、清空列表、一键自动处理并导出。
- `app/pages/desensitization_page.py`：数据脱敏页，支持批处理、进度和日志展示。
- `app/pages/process_page.py`：处理状态示例页（当前为模拟），用于未来接入真实处理任务进度。
- `app/pages/export_page.py`：导出结果示例页（当前为模拟），用于未来接入真实导出逻辑。

- `app/widgets/`：可复用 UI 组件层。
- `app/widgets/file_list_widget.py`：文件列表组件，负责文件路径展示和去重添加。
- `app/widgets/log_widget.py`：日志组件，提供只读、可追加的日志输出能力。
- `app/widgets/card_button.py`：卡片按钮组件，统一首页工具卡片交互样式。

- `app/resources/styles.qss`：全局样式文件，统一配色、按钮状态、导航高亮、卡片与页面视觉风格。
- `app/resources/icons/`：应用图标与品牌图片资源目录（如 `logo.png`、`logo.ico`、`quan_ming.png`）。
- `app/resources/sql/bootstrap_sqlite.sql`：初始化 SQLite 核心表的 SQL。
- `app/services/desensitization/desensitizer_service.py`：数据脱敏服务入口模块。
- `app/services/integration/factory.py`：按来源类型（bank/commercial/other）选择对应服务实现。
- `app/services/integration/bank/ingest_service.py`：银行来源导入（含表头自动识别、伪 `.xls` HTML 识别）。
- `app/services/integration/bank/mapping_service.py`：银行来源标准化写入服务。
- `app/services/integration/bank/export_service.py`：银行全字段合并导出服务（单工作表，逐行“数据来源”追溯）。
- `app/services/integration/commercial/`：商务网来源服务目录（流程上与银行入口分流，导出同为单工作表）。
- `app/services/integration/common/bootstrap.py`：本地 SQLite 表结构初始化执行器。
- `app/services/shared/db/sqlite_client.py`：SQLite 连接与事务封装（全工具共用）。
- 数据整合来源区分：`bank`（银行数据）、`commercial`（商务网数据）、`other`（其他数据）。
- 商务网入口默认不写入银行标准层，仅做原始层入库与全字段合并导出。
- `requirements.txt`：Python 依赖清单。
- `version.txt`：版本元信息文件，记录当前交付版本号、构建时间、可执行文件名和发布说明。
- `.gitignore`：Git 忽略规则。
- `README.md`：项目说明与使用文档。

## 打包为 .exe（Windows）

先安装打包工具：

```bash
pip install pyinstaller
```

执行打包命令（窗口程序、单文件、使用指定图标与命名）：

```bash
python -m PyInstaller --noconfirm --clean --windowed --onefile --icon "app/resources/icons/logo.ico" --version-file "version.txt" --add-data "app/resources;app/resources" --name "数据处理工具-广东电力开发有限公司-版本v1.0.0" main.py
```

打包完成后可执行文件默认位于 `dist/` 目录，例如：

- `dist/数据处理工具-广东电力开发有限公司-版本vx.x.x.exe`

建议在项目根目录下固定一个发布文件夹（例如 `release/`）用于存放最终交付版本，避免和临时构建文件混在一起。

PowerShell 示例（打包后自动归档到 `release/`）：

```powershell
New-Item -ItemType Directory -Force -Path "release" | Out-Null
pyinstaller --noconfirm --clean --windowed --onefile --icon "app/resources/icons/logo.ico" --name "数据处理工具-广东电力开发有限公司-版本vx.x.x" main.py
Copy-Item "dist/数据处理工具-广东电力开发有限公司-版本vx.x.x.exe" "release/"
Copy-Item "version.txt" "release/"
```

执行后目录说明：

- `dist/`：PyInstaller 默认输出目录（每次打包会刷新）
- `build/`：PyInstaller 构建中间文件
- `release/`：你自己保存“可交付安装包/可执行文件”的目录（建议对外发送这个目录下的 `.exe + version.txt`）

## 离线 SQLite 运行说明

### 1) 准备环境

- SQLite 为 Python 内置，无需单独安装数据库服务。
- 项目会在根目录自动生成本地数据库文件：`datafusionx.sqlite3`。

### 2) 安装依赖

```bash
pip install -r requirements.txt
```

### 3) 启动工具并初始化库表

```bash
python main.py
```

- 点击 `导出全字段合并` 时会自动执行初始化（无需手动点“初始化数据库”）。

### 5) 银行/商务网数据整合与导出

- 添加 `.xlsx/.xls` 文件（支持多 sheet、支持拖拽、支持“伪 `.xls`（HTML）”识别）。
- 点击 `导出全字段合并`：自动执行初始化 -> 入库 -> （银行入口标准化 / 商务网入口跳过标准化）-> 导出 `.xlsx`。
- 银行与商务网导出文件均仅包含一个工作表 `全字段合并`：
  - 首列 `数据来源`：逐行对应“原文件名(去扩展)+工作表名”
  - 银行导出会对连续相同 `数据来源` 做纵向合并单元格
  - 后续列：本批次识别到的业务字段并集（商务网按固定输出列对齐）
  - 默认样式：冻结首行、列宽按内容自适应、单元格自动换行，确保内容完整展示
### 5) 备份建议（离线）

- 直接备份项目根目录的 `datafusionx.sqlite3`。
- 建议每天复制一份到 `backup/` 目录并按日期命名。

## 后续规划

- Excel 解析能力接入
- 多源数据融合流程编排
- 插件化扩展机制（工具动态注册）
- 打包为 Windows `.exe` 分发
