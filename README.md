# SwarmCraft v1.0.0

基于 ROS2 + PX4 XRCE-DDS + FastAPI + React + Docker 的多无人机仿真控制平台。

## 系统架构

```
┌─────────────────────────────────────────────────┐
│              前端 (React + Vite)                  │
│  状态监控 · 任务规划 · 编队管理 · 地图可视化       │
└─────────────────────────────────────────────────┘
                      ↕ HTTP / WebSocket
┌─────────────────────────────────────────────────┐
│           业务层 (Python / FastAPI)               │
│  api_server.py · mission_executor.py             │
│  ws_bridge.py (ROS2 → WebSocket JSON)            │
└─────────────────────────────────────────────────┘
                      ↕ XRCE-DDS (UDP :8888)
┌─────────────────────────────────────────────────┐
│           仿真层 (PX4 SITL + Gazebo)              │
│  多机 SITL · XRCE-DDS Agent · Gazebo Classic     │
└─────────────────────────────────────────────────┘

MySQL 8.0 (数据持久化)
```

## 部署

### 环境要求

- Linux (推荐 Ubuntu 20.04/22.04)
- Docker 20.10+ 及 Docker Compose 2.0+
- 至少 8GB RAM，20GB 磁盘空间
- 如需 GUI：X11 显示服务

### 步骤

```bash
# 1. 克隆项目
git clone <repo-url> UAV
cd UAV

# 2. 构建并启动所有服务（首次构建约 20-30 分钟）
docker compose up -d --build

# 3. 等待所有服务就绪（SITL 启动需要 1-2 分钟）
docker compose logs -f bridge | grep "All services running"

# 4. 浏览器访问
# http://localhost:3000
```

### 启动/停止

```bash
# 启动
docker compose up -d

# 查看日志
docker compose logs -f

# 停止
docker compose down

# 停止并清除数据库（完全重置）
docker compose down -v
```

### 无头模式（服务器部署，不显示 Gazebo 窗口）

```bash
HEADLESS=1 docker compose up -d
```

### 开启 Gazebo GUI（本地桌面）

```bash
# 确保 X11 转发可用
xhost +local:docker
HEADLESS=0 docker compose up -d
```

## 服务端口

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端 | http://localhost:3000 | React 管理界面 |
| API | http://localhost:8000 | FastAPI REST 接口 |
| API 文档 | http://localhost:8000/docs | Swagger UI |
| WebSocket | ws://localhost:9090 | 无人机实时遥测 |
| MySQL | localhost:3306 | 数据库 |

## 使用流程

### 1. 创建编队

进入「编队控制」页面，勾选 2 架以上无人机，点击「创建编队」。编队是无人机分组，便于统一分配任务。

### 2. 创建任务

进入「任务规划」页面：
- 点击「新建任务」
- 输入任务名称
- 选择执行无人机（单机或编队）
- 在地图上点击添加航点
- 选择编队时支持「共享航点」（所有无人机相同）或「分派航点」（每架独立）
- 点击「保存任务」

### 3. 执行任务

在任务列表点击「启动」，系统自动：
1. 切换到 OFFBOARD 模式
2. 解锁无人机
3. 起飞到第一个航点高度
4. 按顺序飞往各航点
5. 到达终点后悬停 3 秒，自动降落

### 4. 手动控制

在「状态监控」页面，选中一架无人机，可进行解锁/锁定、起飞/降落、模式切换、返航等操作。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DRONE_COUNT` | 4 | 无人机数量 |
| `HEADLESS` | 0 | 0=显示 Gazebo GUI, 1=无头 |
| `PX4_HOME_LAT` | 34.23 | 起飞点纬度 |
| `PX4_HOME_LON` | 108.95 | 起飞点经度 |
| `PX4_HOME_ALT` | 488.0 | 起飞点海拔(m) |
| `DB_ROOT_PASS` | uav123456 | 数据库密码 |

## 数据库

### 核心表

| 表名 | 说明 |
|------|------|
| `vehicles` | 飞行器注册信息 |
| `swarm_mission` | 编队（无人机分组） |
| `mission` | 任务（每架无人机一条记录） |
| `waypoint` | 航点序列（ENU 坐标） |
| `flight_logs` | 飞行日志 |
| `command_control` | 控制指令记录 |

### 直接查询

```bash
docker exec uav-mysql mysql -uroot -puav123456 -e "SELECT mission_id, vehicle_id, task_name, status FROM uav_swarm.mission;"
```

## 故障排查

```bash
# 健康检查
curl http://localhost:8000/health

# 各服务日志
docker logs uav-bridge --tail 50
docker logs uav-sitl --tail 50

# 任务执行器日志
docker exec uav-bridge cat /tmp/mission_executor.log

# API 日志
docker exec uav-bridge cat /tmp/api_server.log

# 检查 ROS2 话题
docker exec uav-bridge bash -c "source /opt/ros/humble/setup.sh && ros2 topic list"

# 重置数据库
docker compose down -v
docker compose up -d
```

## 技术栈

- **ROS2 Humble** + **XRCE-DDS** (PX4-ROS2 通信，UDP :8888)
- **FastAPI** + **Uvicorn** (HTTP API)
- **React 18** + **Vite** + **Leaflet** (前端)
- **PX4 v1.14.3** + **Gazebo Classic** (SITL 仿真)
- **MySQL 8.0** (Docker volume 持久化)
- **Micro-ROS Agent** (XRCE-DDS 桥接)

## 许可证

仅供学习和研究使用。

---

v1.0.0 · 2026-05-08
