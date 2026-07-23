# geg-inspector

geg-inspector 是一个面向本地化、离线化数据治理场景的数据整合与综合分析平台。项目以 **FastAPI + React + SQLite + Docker Compose** 为核心，支持将银行流水、工商主体、商务网询价、微信转账、通信话单等多源异构数据导入到统一的数据底座中，并提供标准化映射、查询分析、风险识别、关系融合、OCR 识别、脱敏处理与报表导出能力。

项目默认以 Docker 方式交付，部署后通过浏览器访问，不依赖外部数据库服务，适合本机、内网服务器或离线环境运行。

---

## 目录

- [项目特性](#项目特性)
- [核心功能](#核心功能)
- [技术架构](#技术架构)
- [技术栈](#技术栈)
- [项目目录说明](#项目目录说明)
- [运行环境要求](#运行环境要求)
- [Docker 部署说明](#docker-部署说明)
- [本地开发说明](#本地开发说明)
- [演示数据与初始化](#演示数据与初始化)
- [运行数据与环境变量](#运行数据与环境变量)
- [企查查配置](#企查查配置)
- [测试与构建](#测试与构建)
- [交付打包](#交付打包)
- [常见问题](#常见问题)

---

## 项目特性

- **离线运行**：默认使用本地 SQLite 文件数据库，部署后不依赖外部数据库、中间件或云服务。
- **多源数据接入**：支持银行流水、工商主体、商务网询价、微信转账、通信话单等数据源。
- **统一数据治理**：围绕案件、批次、数据集、字段映射、标准化表进行统一管理。
- **关系融合分析**：支持跨数据源识别人员、手机号、账号、企业等关键标识，并进行自动关联与人像归并。
- **融合研判中枢**：融合分析驾驶舱、多层关系图探索、风险事件扫描与研判模型配置。
- **数据中心看板**：全库数据概览、趋势图表、关联人物排名与跨批次记录治理。
- **银行 OCR 辅助录入**：支持银行流水图片或 PDF OCR、版式解析、人工校对与入库。
- **风险识别与报告导出**：支持商务网风险规则识别、银行流水分析、通信/微信数据分析与结果导出。
- **Docker 一键部署**：前端 nginx 与后端 FastAPI 容器化部署，启动脚本适配 Windows、macOS 和 Linux。
- **适合 GitHub 展示与二次开发**：前后端分离、业务模块清晰、测试用例覆盖核心服务。

---

## 核心功能

### 1. 案件与批次管理

- 创建和管理分析案件。
- 按批次导入不同来源的数据文件。
- 查看批次、数据表、导入记录与处理状态。
- 支持导入数据清理、预览和重新处理。

### 2. 银行流水分析

- 支持银行流水 Excel/表格文件导入。
- 支持银行模板录入、字段映射与用户自定义模板。
- 提供收支统计、交易对手分析、金额区间筛选、时间筛选等能力。
- 支持标准化后的银行流水查询与结果导出。

### 3. 银行 OCR 识别与校对

- 支持上传银行流水图片、PDF、表格等材料。
- 支持 OCR 识别、图片预处理、版式解析与表格行解析。
- 支持人工校对识别结果。
- 支持将校对后的流水提交到标准化银行流水数据表。

### 4. 商务网询价分析

- 支持商务网询价数据导入、字段映射与标准化。
- 支持企业维度、人员维度、交易维度统计分析。
- 支持异常询价、频繁询价、关联风险等规则识别。
- 支持商务分析结果和风险报告导出。

### 5. 工商主体与企查查能力

- 支持工商主体信息导入。
- 支持企业名称匹配、企业基础信息补充。
- 支持通过企查查配置进行企业信息查询与导出。

### 6. 微信转账与通信话单分析

- 支持微信转账记录导入、映射、分析和导出。
- 支持通信话单导入、运营商模板识别、号码标准化、通联统计与导出。
- 支持与其他数据源进行人员、手机号、企业等标识融合。

### 7. 多源数据融合与研判中心

- 自动发现多数据源中的关键标识，如姓名、手机号、账号、企业名称等。
- 对不同来源数据进行实体关联与人像归并（人物关系专题）。
- 融合分析驾驶舱：单人全景、双人关系、标识符自由检索与记录详情抽屉。
- 关系图探索：多层扩张、路径发现、关系过滤与观测状态本地持久化。
- 事件管理：按已启用研判模型扫描案件数据，展示大额转账、围标等触发事件。
- 模型管理：配置银行流水、微信转账、商务网与围串标风险模型的启用与参数。
- 案件工作流：新建案件、打开案件、导出案件与案件批次维护。

### 8. 数据中心

- 数据看板：全库/按案件的数据概览、来源分布、趋势图表与关联人物排名。
- 数据管理：跨批次记录查询、筛选与批量删除，支持案件与批次维度治理。
- 与案件、批次、数据表浏览等数据管理入口协同，形成统一数据底座视图。

### 9. 数据脱敏

- 支持对常见文件进行敏感字段脱敏处理。
- 支持文件或文件夹级处理。
- 可用于数据外发、报告交付前的隐私保护。

---

## 技术架构

```text
┌─────────────────────────────────────────────────────────────┐
│                         Browser                              │
│              React + TypeScript + Ant Design                 │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / REST API
┌──────────────────────────────▼──────────────────────────────┐
│                         nginx                                │
│        静态资源服务 / API 反向代理 / 容器入口 8080             │
└──────────────────────────────┬──────────────────────────────┘
                               │ /api
┌──────────────────────────────▼──────────────────────────────┐
│                       FastAPI Backend                         │
│     API 路由 / 应用用例层 / 业务服务层 / 文件导入导出          │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                     Local Runtime Storage                     │
│       SQLite 数据库 / uploads 上传缓存 / exports 导出文件      │
└─────────────────────────────────────────────────────────────┘
```

后端采用分层结构：

- **API 层**：`backend/main.py` 负责 FastAPI 路由、请求模型、接口响应与静态文件返回。
- **Application 用例层**：`backend/app/application/` 组织导入、分析、导出、案件、融合、OCR 等业务用例。
- **Service 服务层**：`backend/app/services/` 提供银行、商务、通信、微信、OCR、融合、脱敏等领域服务。
- **Resource 资源层**：`backend/app/resources/` 保存 SQL 初始化脚本和配置示例。
- **Runtime 运行路径层**：`backend/app/runtime_paths.py` 统一管理数据库、上传、导出和日志目录。

---

## 技术栈

### 后端

- Python 3.10+
- FastAPI
- Uvicorn
- SQLite
- pandas
- openpyxl / xlrd
- python-multipart
- httpx
- python-docx
- matplotlib
- PaddleOCR / PaddlePaddle
- OpenCV headless
- pdf2image
- Pillow
- cairosvg

### 前端

- React 18
- TypeScript
- Vite 5
- Ant Design 5
- ECharts / echarts-for-react
- React Router
- @dnd-kit

### 部署与运行

- Docker
- Docker Compose
- nginx
- 本地文件持久化目录 `data/`

---

## 项目目录说明

```text
geg-inspector/
├── backend/                              # 后端 FastAPI 服务
│   ├── __init__.py
│   ├── main.py                           # FastAPI 应用入口，集中定义 REST API
│   ├── Dockerfile                        # 后端 Docker 构建文件
│   ├── scripts/                          # 后端辅助脚本
│   │   └── download_paddleocr_models.py   # PaddleOCR 模型下载脚本
│   ├── tests/                            # 后端单元测试与集成测试
│   │   ├── test_application_use_cases.py  # 应用用例层测试
│   │   ├── test_backend_api.py            # API 测试
│   │   ├── test_bank_analysis_modules.py  # 银行分析模块测试
│   │   ├── test_bank_ocr.py               # 银行 OCR 流程测试
│   │   ├── test_commercial_risk_rules.py  # 商务风险规则测试
│   │   ├── test_fusion.py                 # 多源融合测试
│   │   ├── test_runtime_paths.py          # 运行路径测试
│   │   ├── test_telecom_integration.py    # 通信话单集成测试
│   │   └── test_user_bank_templates.py    # 用户银行模板测试
│   └── app/                              # 后端主应用代码
│       ├── runtime_paths.py              # 数据库、上传、导出、日志路径管理
│       ├── application/                  # 应用用例层
│       │   ├── analysis_use_cases.py      # 银行、商务、通信、微信分析用例
│       │   ├── bank_ocr_use_cases.py      # 银行 OCR 识别、校对、提交用例
│       │   ├── bootstrap.py               # 数据库启动初始化
│       │   ├── case_use_cases.py          # 案件管理用例
│       │   ├── dataset_use_cases.py       # 数据集、批次、表预览用例
│       │   ├── export_use_cases.py        # 导出用例
│       │   ├── data_center_use_cases.py   # 数据中心看板与记录治理用例
│       │   ├── fusion_use_cases.py        # 多源融合用例
│       │   ├── import_use_cases.py        # 文件导入与标准化用例
│       │   ├── risk_config_use_cases.py   # 风险规则配置用例
│       │   └── task_store.py              # 后台任务状态管理
│       ├── resources/                    # 初始化 SQL 与配置示例
│       │   ├── config/                    # db、企查查等配置示例
│       │   └── sql/                       # SQLite/PostgreSQL 初始化脚本
│       └── services/                     # 领域服务层
│           ├── bank_ocr/                  # 银行流水 OCR、图片预处理、PDF 转换、表格解析
│           ├── data_center/               # 数据中心看板统计与记录治理
│           ├── desensitization/           # 数据脱敏服务
│           ├── fusion/                    # 标识发现、自动关联、图探索、事件与模型管理
│           ├── integration/               # 各数据源集成服务
│           │   ├── bank/                  # 银行流水模板、导入、映射、查询、分析、导出
│           │   ├── commercial/            # 商务网询价、工商主体、风险规则、导出
│           │   ├── common/                # 集成服务公共能力
│           │   ├── telecom/               # 通信话单导入、运营商模板、号码工具、分析、导出
│           │   └── wechat/                # 微信转账导入、映射、分析、导出
│           └── shared/                    # 数据库客户端等共享基础设施
│
├── frontend/                             # 前端 React 应用
│   ├── Dockerfile                        # 前端 Docker 构建文件
│   ├── nginx.conf                        # nginx 静态资源与 /api 反向代理配置
│   ├── package.json                      # 前端依赖与 npm 脚本
│   ├── package-lock.json                 # npm 锁定文件
│   ├── tsconfig.json                     # TypeScript 配置
│   ├── vite.config.ts                    # Vite 配置
│   ├── index.html                        # 前端 HTML 入口
│   └── src/                              # 前端源码
│       ├── App.tsx                       # 应用路由与整体布局
│       ├── api.ts                        # 后端 API client
│       ├── main.tsx                      # React 入口
│       ├── theme.ts                      # Ant Design 主题配置
│       ├── styles.css                    # 全局样式
│       ├── components/                   # 复用组件
│       │   ├── AnalysisDateTimeFilters.tsx # 分析时间筛选组件
│       │   ├── WorkflowGuide.tsx          # 工作流引导组件
│       │   ├── data-import/               # 数据导入表单与辅助逻辑
│       │   └── fusion/                    # 融合研判、事件/模型、人像关联等面板
│       ├── utils/                        # 图探索观测存储、记录解析等工具
│       └── pages/                        # 业务页面
│           ├── HomePage.tsx              # 首页/导航页
│           ├── CaseManagePage.tsx        # 案件管理
│           ├── ImportPage.tsx            # 数据导入入口
│           ├── BatchesPage.tsx           # 批次管理
│           ├── TablesPage.tsx            # 数据表浏览
│           ├── DataDashboardPage.tsx     # 数据中心 · 数据看板
│           ├── DataManagePage.tsx        # 数据中心 · 数据管理
│           ├── BankAnalysisPage.tsx      # 银行流水分析
│           ├── BankTemplatesPage.tsx     # 银行模板管理
│           ├── BankOcrProofreadPage.tsx  # 银行 OCR 校对
│           ├── CommercialAnalysisPage.tsx # 商务网分析
│           ├── CommercialRiskPage.tsx    # 商务风险分析
│           ├── QichachaIcPage.tsx        # 企查查/工商信息页面
│           ├── TelecomAnalysisPage.tsx   # 通信话单分析
│           ├── WechatAnalysisPage.tsx    # 微信转账分析
│           ├── FusionAnalysisHubPage.tsx # 研判中心 · 融合分析中枢
│           ├── FusionCockpitPage.tsx     # 融合分析驾驶舱
│           ├── GraphExplorePage.tsx      # 关系图探索
│           ├── PersonLinkingPage.tsx     # 人物关系 · 人像归并
│           └── DesensitizationPage.tsx   # 数据脱敏
│
├── mock-data/                            # 演示数据
│   ├── README.md                         # 演示数据说明
│   ├── 01_enterprise_工商主体.xlsx
│   ├── 02_commercial_商务网询价.xlsx
│   ├── 03_bank_多人流水_建设银行.xlsx
│   ├── 04_wechat_多人转账.xlsx
│   └── 05_telecom_多人话单.xlsx
│
├── scripts/                              # 项目辅助脚本
│   ├── build_docker_package.sh           # macOS/Linux Docker 交付包构建脚本
│   ├── build_docker_package.ps1          # Windows Docker 交付包构建脚本
│   ├── generate_mock_data.py             # 生成演示数据
│   └── import_mock_data.py               # 导入演示数据
│
├── data/                                 # 运行时数据目录，通常不提交 Git
│   ├── geg-inspector.sqlite3               # SQLite 数据库，运行后自动生成
│   ├── uploads/                          # 上传文件缓存
│   └── exports/                          # 导出结果，可随运行配置变化
│
├── docker-compose.yml                    # 默认 Docker Compose 部署配置
├── docker-compose.mirror.cn.yml          # 国内镜像/构建加速 Compose 覆盖配置
├── README-DOCKER.md                      # 面向交付用户的 Docker 部署文档
├── requirements.txt                      # Python 后端依赖
├── .dockerignore                         # Docker 构建忽略规则
├── .gitignore                            # Git 忽略规则
├── start.sh                              # macOS/Linux 一键启动
├── stop.sh                               # macOS/Linux 一键停止
├── start-mirror.sh                       # macOS/Linux 国内镜像启动
├── start.bat                             # Windows 一键启动
├── stop.bat                              # Windows 一键停止
├── start-mirror.bat                      # Windows 国内镜像启动
├── dev.sh                                # macOS/Linux 本地前后端同时启动
├── dev.bat                               # Windows 本地前后端同时启动
└── version.txt                           # 项目版本号
```

> 说明：`data/`、上传缓存、导出文件、数据库文件、系统临时文件等运行产物不建议提交到 GitHub。提交前请确认 `.gitignore` 已正确排除本地运行数据和敏感配置。

---

## 运行环境要求

### Docker 部署环境

- Docker 24+
- Docker Compose v2+
- 建议内存：4GB 以上
- 建议磁盘：10GB 以上可用空间
- 浏览器：Chrome / Edge / Firefox 最新版

### 本地开发环境

- Python 3.10 或更高版本
- Node.js 18 或更高版本
- npm 9 或更高版本
- macOS、Linux 或 Windows

### OCR 相关依赖

银行 OCR 功能依赖 PaddleOCR、PaddlePaddle、OpenCV、pdf2image 等组件。若仅使用常规 Excel 数据导入分析，可不重点关注 OCR 模型；若需要 OCR，请确保模型文件和系统图像处理依赖可用。

---

## Docker 部署说明

Docker 是当前项目推荐的部署和交付方式。

### 1. 克隆项目

```bash
git clone https://github.com/<your-org-or-user>/geg-inspector.git
cd geg-inspector
```

### 2. 一键启动

#### macOS / Linux

```bash
chmod +x start.sh stop.sh start-mirror.sh
./start.sh
```

国内网络环境可使用：

```bash
./start-mirror.sh
```

#### Windows

双击运行：

```text
start.bat
```

国内网络环境可双击：

```text
start-mirror.bat
```

### 3. 访问系统

启动完成后，在浏览器访问：

```text
http://localhost:8080
```

后端健康检查地址：

```text
http://localhost:8080/api/health
```

### 4. 手动 Docker Compose 命令

默认启动：

```bash
docker compose up -d --build
```

使用国内镜像覆盖配置启动：

```bash
docker compose -f docker-compose.yml -f docker-compose.mirror.cn.yml up -d --build
```

查看容器状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

停止并重新构建：

```bash
docker compose down
docker compose up -d --build
```

### 5. Docker 数据持久化

`docker-compose.yml` 默认将本地目录挂载到容器内：

```yaml
volumes:
  - ./data:/data
```

因此运行数据会保存在项目根目录的 `data/` 下。删除容器不会删除 `data/` 中的数据库、上传缓存和导出文件。

Docker 模式下默认路径：

```text
/data/data/geg-inspector.sqlite3
/data/data/uploads/
/data/exports/
/data/logs/
```

对应到宿主机项目目录：

```text
./data/geg-inspector.sqlite3
./data/uploads/
./exports/
./logs/
```

---

## 本地开发说明

### 一键启动前后端（推荐）

在仓库根目录执行：

```bash
./dev.sh
```

Windows：

```bat
dev.bat
```

会同时启动：

- 后端：`http://127.0.0.1:8765`（自动 `--reload`）
- 前端：`http://127.0.0.1:5173`

按 `Ctrl+C`（macOS/Linux）可同时关闭两端。默认管理员账号：`admin` / `admin123`。

### 1. 安装后端依赖

建议使用虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. 单独启动后端

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765 --reload
```

后端 API 默认地址：

```text
http://127.0.0.1:8765/api
```

健康检查：

```text
http://127.0.0.1:8765/api/health
```

### 3. 安装前端依赖

```bash
cd frontend
npm install
```

### 4. 单独启动前端开发服务器

```bash
npm run dev
```

开发环境访问：

```text
http://127.0.0.1:5173
```

前端开发环境通过 Vite 代理访问后端 API。

---

## 演示数据与初始化

项目提供 `mock-data/` 目录用于功能演示和开发调试。

### 演示数据内容

```text
mock-data/
├── 01_enterprise_工商主体.xlsx       # 工商主体数据
├── 02_commercial_商务网询价.xlsx     # 商务网询价数据
├── 03_bank_多人流水_建设银行.xlsx    # 银行流水数据
├── 04_wechat_多人转账.xlsx           # 微信转账数据
└── 05_telecom_多人话单.xlsx          # 通信话单数据
```

### 生成演示数据

```bash
python scripts/generate_mock_data.py
```

### 导入演示数据

在后端服务启动后执行：

```bash
python scripts/import_mock_data.py
```

也可以在前端页面中通过“文件导入”功能手动上传 `mock-data/` 中的数据文件。

---

## 运行数据与环境变量

后端通过 `backend/app/runtime_paths.py` 统一管理运行路径。

### 默认路径

开发模式下，默认运行数据位于项目根目录：

```text
data/geg-inspector.sqlite3
data/uploads/
exports/
logs/
```

Docker 模式下，`GEG_INSPECTOR_HOME=/data`，对应容器内路径：

```text
/data/data/geg-inspector.sqlite3
/data/data/uploads/
/data/exports/
/data/logs/
```

### 常用环境变量

| 环境变量 | 说明 | 示例 |
| --- | --- | --- |
| `DATAFUSIONX_HOME` | 指定运行数据根目录 | `/data` |
| `GEG_INSPECTOR_DB_PATH` | 指定 SQLite 数据库文件路径，优先级最高 | `/data/data/geg-inspector.sqlite3` |
| `GEG_INSPECTOR_HOST` | 后端监听地址 | `0.0.0.0` |
| `GEG_INSPECTOR_BACKEND_PORT` | 后端监听端口 | `8765` |
| `QICHACHA_APP_KEY` | 企查查 AppKey | `your_app_key` |
| `QICHACHA_SECRET_KEY` | 企查查 SecretKey | `your_secret_key` |

数据库路径优先级：

```text
GEG_INSPECTOR_DB_PATH / DATAFUSIONX_DB_PATH > GEG_INSPECTOR_HOME/data/geg-inspector.sqlite3 > 项目根目录/data/geg-inspector.sqlite3
```

### 数据备份建议

建议定期备份：

```text
data/
```

其中通常包含：

- SQLite 数据库
- 上传文件缓存
- 导出结果
- 运行日志
- 本地配置文件

---

## 企查查配置

如果需要使用企查查相关能力，可以通过环境变量配置：

macOS / Linux：

```bash
export QICHACHA_APP_KEY="你的 AppKey"
export QICHACHA_SECRET_KEY="你的 SecretKey"
```

Windows PowerShell：

```powershell
$env:QICHACHA_APP_KEY="你的 AppKey"
$env:QICHACHA_SECRET_KEY="你的 SecretKey"
```

也可以在运行数据目录中放置：

```text
data/qichacha_config.json
```

配置格式可参考：

```text
backend/app/resources/config/qichacha_config.example.json
```

> 注意：不要将真实 AppKey、SecretKey、数据库文件、客户数据或导出结果提交到 GitHub。

---

## 测试与构建

### 后端测试

```bash
python -m unittest discover -s backend/tests -t backend
```

### 前端类型检查与构建

```bash
npm --prefix frontend run build
```

### 后端开发启动检查

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765 --reload
```

### Docker 构建检查

```bash
docker compose up -d --build
docker compose ps
```

---

## 交付打包

项目提供 Docker 交付包构建脚本，适合打包后发给内网或离线用户。

### macOS / Linux

```bash
chmod +x scripts/build_docker_package.sh
./scripts/build_docker_package.sh
```

### Windows PowerShell

```powershell
.\scripts\build_docker_package.ps1
```

打包产物默认输出到：

```text
dist/geg-inspector-docker.zip
```

交付包通常包含：

- Docker Compose 配置
- 前后端 Dockerfile
- 启停脚本
- 部署说明
- 必要的源码与配置文件

详细部署文档见：

```text
README-DOCKER.md
```

---

## GitHub 提交前检查清单

同步到 GitHub 前建议确认：

- `.gitignore` 已排除 `data/`、数据库、日志、上传文件、导出文件、系统缓存等运行产物。
- 未提交真实客户数据、隐私数据、接口密钥或本地配置文件。
- `README.md`、`README-DOCKER.md` 与启动脚本保持一致。
- `npm --prefix frontend run build` 可正常通过。
- `python -m unittest discover -s backend/tests -t backend` 可正常通过。
- Docker 模式可通过 `docker compose up -d --build` 正常启动。

---

## 常见问题

### 1. 启动后访问不了 `http://localhost:8080`

请先检查容器状态：

```bash
docker compose ps
```

再查看日志：

```bash
docker compose logs -f
```

如果端口 8080 被占用，可以修改 `docker-compose.yml`：

```yaml
ports:
  - "8081:80"
```

然后访问：

```text
http://localhost:8081
```

### 2. 后端健康检查失败

检查后端日志：

```bash
docker compose logs -f backend
```

常见原因包括：

- Python 依赖安装失败。
- OCR 相关依赖下载较慢。
- 数据目录权限不足。
- 端口或容器网络异常。

### 3. Docker 构建速度慢

国内网络环境建议使用镜像启动脚本：

```bash
./start-mirror.sh
```

或使用 Compose 覆盖配置：

```bash
docker compose -f docker-compose.yml -f docker-compose.mirror.cn.yml up -d --build
```

### 4. 如何重置本地数据

停止服务后，备份并删除 `data/` 目录，再重新启动：

```bash
docker compose down
mv data data_backup
docker compose up -d --build
```

> 删除 `data/` 会清空本地数据库、上传缓存和导出文件，请务必提前备份。

### 5. 如何备份数据

直接复制项目根目录下的 `data/` 目录即可。建议定期备份到外部磁盘或内网备份服务器。

---

## License

当前仓库尚未声明开源许可证。如需公开发布到 GitHub，请根据项目规划补充 `LICENSE` 文件，并在本节中说明授权方式。
