# OpenTapNow

前后端分离的单页应用，支持 Docker 一键部署，内置 MySQL 数据库支持。

## 项目结构

```
├── src/              # React 前端源码
├── localserver/      # Python 后端服务
├── Dockerfile        # 统一镜像构建
├── docker-compose.yml # 部署配置（默认外部 MySQL）
├── docker-compose.mysql.yml # 内置 MySQL 叠加配置
├── .env.example      # 环境变量配置模板
├── package.json      # 前端依赖
└── README.md         # 本文档
```

## 容器化部署（详细步骤）

### 0) 前置准备

1. 已安装 Docker Desktop（含 Compose v2）。
2. 确认端口可用：
   - `8080`（应用入口）
   - `3306`（仅在启用内置 MySQL 时需要）
3. 在项目根目录执行命令。

### 1) 初始化配置文件

```bash
# 1. 复制环境变量模板
cp .env.example .env

# 2. （重要）设置默认管理员账号（必须设置强密码）
# TAPNOW_DEFAULT_ADMIN_USER=admin
# TAPNOW_DEFAULT_ADMIN_PASSWORD=please-change-me
```

编辑 `.env`，至少确认以下变量：

```env
# 必填：数据库连接（方式A：已有 MySQL）
# 示例：mysql+pymysql://user:password@db-host:3306/tapnow_db?charset=utf8mb4
TAPNOW_DATABASE_URL=

# 管理员账号（首次启动会自动创建）
TAPNOW_DEFAULT_ADMIN_USER=admin
TAPNOW_DEFAULT_ADMIN_PASSWORD=please-change-me
```

### 2) 选择数据库部署模式（二选一）

#### 方式 A：使用已有 MySQL（默认推荐）

适用场景：你已有本地/内网/云端 MySQL，不希望再起一个数据库容器。

```bash
# 1. 确保 .env 里的 TAPNOW_DATABASE_URL 指向你的 MySQL

# 2. 启动应用容器
docker compose up -d --build

# 3. 查看日志（确认后端连接数据库成功）
docker compose logs -f tapnow

# 4. 访问应用
# http://localhost:8080
```

#### 方式 B：启用内置 MySQL（可选）

适用场景：新环境快速启动，不依赖外部数据库。

```bash
# 1. 使用基础文件 + mysql 叠加文件启动
docker compose -f docker-compose.yml -f docker-compose.mysql.yml up -d --build

# 2. 查看 mysql 与 tapnow 日志
docker compose -f docker-compose.yml -f docker-compose.mysql.yml logs -f mysql tapnow

# 3. 访问应用
# http://localhost:8080
```

说明：
- `docker-compose.yml`：仅启动 `tapnow`，默认连外部库。
- `docker-compose.mysql.yml`：额外启动 `mysql`，并自动把 `tapnow` 指向 `mysql:3306`。

### 3) 首次启动后检查清单

1. 打开 `http://localhost:8080`。
2. 使用你设置的管理员账号登录。
3. 若登录失败，先检查：
   - `.env` 的 `TAPNOW_DATABASE_URL` 是否正确。
   - MySQL 用户是否有建表权限。
4. 查看容器状态：

```bash
docker compose ps
```

### 4) 常见运维命令

#### 仅外部 MySQL 模式（方式 A）

```bash
# 重启应用
docker compose restart tapnow

# 停止应用
docker compose down

# 更新镜像并重建
docker compose up -d --build
```

#### 内置 MySQL 模式（方式 B）

```bash
# 停止应用 + 内置数据库
docker compose -f docker-compose.yml -f docker-compose.mysql.yml down

# 谨慎：删除容器同时删除 mysql 数据卷
docker compose -f docker-compose.yml -f docker-compose.mysql.yml down -v
```

### 5) 单镜像运行（不使用 compose）

适合快速演示；建议连接外部 MySQL（通过 `TAPNOW_DATABASE_URL`）。

```bash
docker build -t tapnow-online:latest .

docker run -d --name tapnow-online \
  -p 8080:8080 \
  -v ./tapnow_data:/app/data \
  -e TAPNOW_DATABASE_URL="mysql+pymysql://tapnow:change-me-db-password@host.docker.internal:3306/tapnow_db?charset=utf8mb4" \
  -e TAPNOW_DEFAULT_ADMIN_USER="admin" \
  -e TAPNOW_DEFAULT_ADMIN_PASSWORD="please-change-me" \
  tapnow-online:latest
```

### 6) 管理员账号说明（分享项目前请先看）

1. 默认管理员来自环境变量：
   - `TAPNOW_DEFAULT_ADMIN_USER`
   - `TAPNOW_DEFAULT_ADMIN_PASSWORD`
2. 首次部署会按上述账号自动创建管理员。
3. 对外分享或公网部署前，务必修改默认密码，避免使用任何弱口令（例如 `admin/123456`）。

### 环境变量

#### 配置文件位置

创建 `.env` 文件（复制 `.env.example`）：

```bash
cp .env.example .env
```

#### 必需配置

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `TAPNOW_DATABASE_URL` | MySQL 连接字符串（外部库模式必填） | `mysql+pymysql://user:password@db-host:3306/tapnow_db?charset=utf8mb4` |
| `TAPNOW_DEFAULT_ADMIN_USER` | 默认管理员用户名 | `admin` |
| `TAPNOW_DEFAULT_ADMIN_PASSWORD` | 默认管理员密码 | `please-change-me` |

#### 仅内置 MySQL 模式推荐配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `MYSQL_ROOT_PASSWORD` | MySQL root 密码 | `change-me-root-password` |
| `TAPNOW_DB_PASSWORD` | MySQL 应用用户密码 | `change-me-db-password` |

#### 可选配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `VITE_LOCAL_SERVER_URL` | 前端构建时覆盖本地服务地址（可选） | 空（自动推断） |
| `TAPNOW_ENABLE_FILE_SERVER` | 启用文件服务 | `true` |
| `TAPNOW_ENABLE_PROXY` | 启用 HTTP 代理 | `true` |
| `TAPNOW_ENABLE_COMFY` | 启用 ComfyUI 中间件 | `false` |
| `TAPNOW_ENABLE_LOG` | 启用日志 | `true` |
| `TAPNOW_STATIC_DIR` | 静态文件目录 | `/app/static` |

## 快速开始（摘要）

```bash
# 外部 MySQL（默认）
docker compose up -d --build

# 内置 MySQL（可选）
docker compose -f docker-compose.yml -f docker-compose.mysql.yml up -d --build
```

## 开发

### 本地调试 (前后端分离)

需要同时启动后端服务和前端开发服务器：

**1. 安装依赖**
```bash
# 前端依赖
npm install

# 后端依赖
cd localserver
pip install -r requirements.txt
```

**2. 配置本地数据库**

创建 `.env` 文件：

```bash
# 使用本地或远程 MySQL
export TAPNOW_DATABASE_URL="mysql+pymysql://user:password@localhost:3306/tapnow_db?charset=utf8mb4"
export TAPNOW_DEFAULT_ADMIN_USER="admin"
export TAPNOW_DEFAULT_ADMIN_PASSWORD="please-change-me"
```

**3. 启动后端服务**（终端1）
```bash
cd localserver
python server.py -p 9527 -d ./data
```

后端启动后会监听 `http://localhost:9527`

**3. 启动前端开发服务器**（终端2）
```bash
npm run dev
```

前端默认地址 `http://localhost:5173`

### 生产构建

```bash
# 构建前端（输出到 dist/）
npm run build

# 启动后端并指定静态文件目录
python localserver/server.py -p 8080 -d ./data --static-dir ./dist
```

### 常用命令

| 命令 | 说明 |
|------|------|
| `npm run dev` | 启动前端开发服务器 |
| `npm run build` | 构建前端 |
| `python server.py -p 9527` | 启动后端服务 |
| `docker compose up -d --build` | Docker 启动所有服务（含构建） |
| `docker compose down` | 停止所有服务 |
| `docker compose logs -f` | 查看实时日志 |

### 调试端口

- `8080` - 统一入口（前端 + API，Docker 模式）
- `5173` - Vite 开发服务器（前端开发）
- `9527` - Python 后端服务（本地开发）
- `3306` - MySQL 数据库（Docker 模式）

## 云服务器部署

```bash
# 1. 在本地构建镜像并导出
docker build -t tapnow-online:latest .
docker save tapnow-online:latest | gzip > tapnow-online.tar.gz

# 2. 上传到服务器
scp tapnow-online.tar.gz user@server:/opt/
scp docker-compose.yml user@server:/opt/tapnow-online/
scp .env.example user@server:/opt/tapnow-online/.env

# 3. 在服务器加载镜像并启动
ssh user@server "cd /opt && docker load < tapnow-online.tar.gz"
ssh user@server "cd /opt/tapnow-online && docker compose up -d --build"
```

## 端口

- `8080` - 统一入口 (前端 + API)
- `3306` - MySQL 数据库

## 数据库说明

### 自动创建的数据表

系统启动时会自动创建以下数据表：

- `users` - 用户账户管理
- `sessions` - 用户认证会话
- `projects` - 项目状态存储
- `assets` - 资源文件元数据和内容
- `workflows` - 工作流定义
- `workflow_versions` - 工作流版本历史
- `audit_logs` - 操作审计日志
- `system_configs` - 系统配置

### 数据库特性

- **持久化存储**：MySQL 数据保存在 Docker 卷 `mysql_data` 中
- **自动迁移**：表结构自动创建，无需手动执行 SQL
- **兼容模式**：未配置数据库时自动降级为文件系统模式

## 数据持久化

Docker 模式使用以下持久化卷：

- `tapnow_data` - 应用数据（上传的文件、缓存等）
- `mysql_data` - MySQL 数据库文件

数据在容器重启后仍然保留。

## 故障排查

### 先确认你当前使用的模式

- 外部 MySQL（默认）：`docker compose up -d --build`
- 内置 MySQL（叠加）：`docker compose -f docker-compose.yml -f docker-compose.mysql.yml up -d --build`

### A. 外部 MySQL 模式（默认）排查命令

```bash
# 1) 查看应用日志（重点看数据库连接报错）
docker compose logs -f tapnow

# 2) 查看当前生效的数据库连接串（PowerShell）
Get-Content .env | Select-String "TAPNOW_DATABASE_URL"

# 3) 确认容器内环境变量是否注入成功
docker compose exec tapnow python -c "import os; print(os.environ.get('TAPNOW_DATABASE_URL',''))"

# 4) 重启应用服务（不重建）
docker compose restart tapnow

# 5) 重新构建并启动
docker compose up -d --build
```

若仍失败，请重点检查：
1. MySQL 主机/端口是否可达（防火墙、白名单、云安全组）。
2. MySQL 账号是否有建表权限（CREATE/ALTER/INSERT/UPDATE）。
3. 连接串是否为 `mysql+pymysql://...` 格式。

### B. 内置 MySQL 模式（docker-compose.mysql.yml）排查命令

```bash
# 1) 查看服务状态
docker compose -f docker-compose.yml -f docker-compose.mysql.yml ps

# 2) 查看 mysql 日志
docker compose -f docker-compose.yml -f docker-compose.mysql.yml logs -f mysql

# 3) 查看 tapnow 日志
docker compose -f docker-compose.yml -f docker-compose.mysql.yml logs -f tapnow

# 4) 在 mysql 容器里测试连接
docker compose -f docker-compose.yml -f docker-compose.mysql.yml exec mysql mysql -u tapnow -p tapnow_db

# 5) 仅重启应用
docker compose -f docker-compose.yml -f docker-compose.mysql.yml restart tapnow

# 6) 重建并启动全部服务
docker compose -f docker-compose.yml -f docker-compose.mysql.yml up -d --build
```

### C. 数据重置（谨慎操作）

#### 外部 MySQL 模式

```bash
# 只重建应用容器，不会删除外部数据库数据
docker compose down
docker compose up -d --build
```

#### 内置 MySQL 模式

```bash
# 删除容器并删除内置 mysql 数据卷（会清空内置数据库）
docker compose -f docker-compose.yml -f docker-compose.mysql.yml down -v
docker compose -f docker-compose.yml -f docker-compose.mysql.yml up -d --build
```

## 技术栈

- **前端**：React 18 + Vite + TailwindCSS
- **后端**：Python 3.11 + SQLAlchemy + PyMySQL
- **数据库**：MySQL 8.0
- **部署**：Docker + Docker Compose
