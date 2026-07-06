# geg-inspector Docker 本地部署

geg-inspector 可通过 Docker 在本机或内网服务器上运行，数据保存在本地，无需公网部署。

## 系统要求

- 已安装并启动 [Docker Desktop](https://www.docker.com/products/docker-desktop/)（Windows / macOS）
- 或 Linux 上已安装 Docker Engine + Docker Compose

## 第一次使用

1. 安装 Docker Desktop 并确保其正在运行
2. 解压 geg-inspector 部署包到任意目录
3. 启动系统（**首次会自动构建镜像，需 10–20 分钟**）：
   - **Windows（国内网络）**：双击 `start-mirror.bat`
   - **Windows（海外/可直连 Docker Hub）**：双击 `start.bat`
   - **macOS / Linux（国内）**：`chmod +x start-mirror.sh && ./start-mirror.sh`
   - **macOS / Linux**：`chmod +x start.sh && ./start.sh`
4. 浏览器打开：

```text
http://localhost:8080
```

## 以后使用

| 操作 | Windows | macOS / Linux |
|------|---------|---------------|
| **启动**（已有镜像，秒开） | 双击 `start-mirror.bat`（国内）或 `start.bat` | `./start-mirror.sh` 或 `./start.sh` |
| **关闭** | 双击 `stop.bat` | `./stop.sh` |
| **重新构建**（更新程序包后） | 双击 `rebuild-mirror.bat`（国内）或 `rebuild.bat` | 手动执行 `docker compose ... up -d --build` |

> **说明**：日常启动脚本**不会**重新构建镜像，也不会再访问 Docker 镜像加速站，避免网络波动导致启动失败。只有首次运行或镜像不存在时才会自动构建。

## 局域网访问

同一局域网内的其他设备可通过本机内网 IP 访问：

```text
http://<内网IP>:8080
```

例如 `http://192.168.1.100:8080`。

## 系统结构

```text
Docker
  ├── frontend   前端服务（nginx，对外 8080）
  └── backend    后端服务（FastAPI + SQLite）
```

- 用户访问：`http://localhost:8080`
- 前端请求后端：同源 `/api`（由 nginx 反代，无需配置 IP）
- 数据保存：`./data/` 目录

## 数据目录说明

后端将 `GEG_INSPECTOR_HOME` 设为 `/data`，对应宿主机的 `./data/` 目录。首次运行后会自动创建：

```text
data/
  data/
    geg-inspector.sqlite3    # SQLite 数据库
    uploads/               # 上传缓存
  exports/                 # 导出文件
  logs/                    # 运行日志
```

## 数据安全

- 系统运行在用户自己的电脑或内网服务器上
- 数据保存在本地 `data/` 目录中
- 数据不会上传到开发者服务器

## 备份与迁移

备份或迁移时，复制整个 `data/` 目录即可。建议定期备份 `data/data/geg-inspector.sqlite3`。

## 企查查配置（可选）

通过环境变量（在 `docker-compose.yml` 的 `backend.environment` 中添加）：

```yaml
QICHACHA_APP_KEY: "你的 AppKey"
QICHACHA_SECRET_KEY: "你的 SecretKey"
```

或在数据目录放置配置文件：

```text
data/data/qichacha_config.json
```

格式参考 `backend/app/resources/config/qichacha_config.example.json`。

## 故障排查

查看后端日志：

```bash
docker compose logs backend
```

查看前端日志：

```bash
docker compose logs frontend
```

健康检查：

```bash
curl http://localhost:8080/api/health
```

应返回 `"status": "ok"`。

常见问题：

| 问题 | 处理方式 |
|------|----------|
| 拉取镜像超时 `auth.docker.io ... i/o timeout` | 见下方「Docker Hub 拉取失败」 |
| 构建时 apt 报 `403 Forbidden`（Debian 包下载失败） | 使用最新版 `start-mirror.bat`；脚本已切换阿里云 apt 源并支持多镜像回退 |
| 构建时 pip 报 `403 Forbidden`（Python 包下载失败） | 同上；pip 已切换阿里云 PyPI 并支持多镜像回退 |
| 端口 8080 被占用 | 修改 `docker-compose.yml` 中 `frontend.ports` 为 `"8081:80"` 等 |
| Docker 未启动 | 先打开 Docker Desktop |
| 首次启动较慢 | 首次会构建镜像，需联网下载基础镜像，请耐心等待 |

### Docker Hub 拉取失败（国内网络常见）

报错示例：

```text
failed to fetch oauth token: Post "https://auth.docker.io/token": dial tcp ...:443: i/o timeout
```

说明本机无法稳定访问 Docker Hub，与项目 Dockerfile 无关。任选一种方式：

**方式 A：使用项目内置镜像加速（推荐，最快）**

```bash
# macOS / Linux
./start-mirror.sh

# Windows
start-mirror.bat

# 或手动
docker compose -f docker-compose.yml -f docker-compose.mirror.cn.yml up -d --build
```

**方式 B：配置 Docker Desktop 镜像加速（一劳永逸）**

1. 打开 Docker Desktop → Settings → Docker Engine
2. 在 JSON 中加入 `registry-mirrors`（保留原有其他配置）：

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1panel.live"
  ]
}
```

3. 点击 Apply & Restart
4. 再执行 `docker compose up -d --build`

**方式 C：使用代理**

若已有 VPN/代理，在 Docker Desktop → Settings → Resources → Proxies 中配置 HTTP/HTTPS 代理后重试。

## 手动命令

```bash
# 构建并启动
docker compose up -d --build

# 仅启动（镜像已构建）
docker compose up -d

# 停止
docker compose down

# 查看运行状态
docker compose ps
```

## 银行流水 OCR（图片/PDF）

除 Excel 外，系统支持**离线 OCR** 导入银行流水扫描件（首期支持光大银行版式）：

1. 在「数据导入」页选择 **银行流水** → **图片/PDF 导入（OCR）**
2. 上传 `.jpg` / `.png` / `.pdf`（多页 PDF 会合并为一个批次）
3. 等待本地 OCR 识别完成后进入 **校对页**，对照原图修正表格
4. 点击 **确认录入**，数据写入与 Excel 导入相同的标准银行流水表

**说明：**

- OCR 在 Docker 后端容器内离线运行，不调用外网 API
- 首次构建后端镜像会下载 PaddleOCR 模型，镜像体积约增加 **800MB–1.2GB**，构建时间会更长
- 识别结果仅为初稿，**校对环节不可省略**，尤其注意金额、日期与对方户名
- **Apple Silicon（M 系列）Docker 构建**：构建阶段默认跳过 OCR 模型预下载（避免 Paddle 段错误）；首次使用 OCR 功能时会联网下载模型到 `data/data/uploads/bank_ocr/` 与 `PADDLEOCR_HOME` 目录，下载完成后即可离线使用
- **x86 Linux 服务器**若需构建期完全离线，可在构建时设置 `PRELOAD_OCR_MODELS=1`（见 `docker-compose.mirror.cn.yml` 注释）

## 开发说明

本部署包面向最终用户。开发者日常联调仍可使用：

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
cd frontend && npm run dev
```

详见项目根目录 [README.md](README.md)。
