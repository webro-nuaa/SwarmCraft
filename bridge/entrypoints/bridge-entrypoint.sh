#!/usr/bin/env bash
set -e

DRONE_COUNT=${DRONE_COUNT:-4}
source /opt/ros/humble/setup.bash
source /px4_ws/install/setup.bash
export ROS_DOMAIN_ID=0
export FASTRTPS_DEFAULT_PROFILES_FILE=/app/fastdds-udp.xml

echo "============================================"
echo " UAV Bridge v3.0 (XRCE-DDS)"
echo " Drones: ${DRONE_COUNT}"
echo "============================================"

cleanup() {
    echo "[BRIDGE] Shutting down..."
    kill 0 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

# 等待数据库就绪
echo "[BRIDGE] Waiting for database..."
until mysqladmin ping -h"${DB_HOST:-localhost}" -P"${DB_PORT:-3306}" -u"${DB_USER:-root}" -p"${DB_PASS:-uav123456}" --silent 2>/dev/null; do
    sleep 1
done
echo "[BRIDGE] Database ready"

# 等待所有无人机的 XRCE-DDS 话题就绪
echo "[BRIDGE] Waiting for XRCE-DDS topics..."
for i in $(seq 0 $((DRONE_COUNT - 1))); do
    topic="/drone_${i}/fmu/out/vehicle_status"
    echo -n "  drone_${i}: "
    for attempt in $(seq 1 60); do
        if ros2 topic list 2>/dev/null | grep -q "$topic"; then
            echo "ready (attempt $attempt)"
            break
        fi
        if [ "$attempt" -eq 60 ]; then
            echo "TIMEOUT - topic not found"
        fi
        sleep 1
    done
done

sleep 2

# 1. 启动 ws_bridge.py（ROS2→WebSocket JSON 遥测）
echo "[BRIDGE] Starting WebSocket Bridge..."
cd /app/backend
python3 ws_bridge.py > /tmp/ws_bridge.log 2>&1 &
WS_BRIDGE_PID=$!
echo "  [WS_BRIDGE] WebSocket on :9090 (PID $WS_BRIDGE_PID)"

sleep 2

# 2. 启动 FastAPI 后端（HTTP API）
echo "[BRIDGE] Starting FastAPI server..."
cd /app/backend
python3 api_server.py > /tmp/api_server.log 2>&1 &
API_PID=$!
echo "  [API] HTTP on :8000 (PID $API_PID)"

sleep 2

# 3. 启动任务执行器
echo "[BRIDGE] Starting Mission Executor..."
python3 mission_executor.py > /tmp/mission_executor.log 2>&1 &
EXECUTOR_PID=$!
echo "  [EXECUTOR] Mission executor started (PID $EXECUTOR_PID)"

sleep 1

echo "============================================"
echo " All services running"
echo "============================================"
echo ""
echo "Services:"
echo "  - XRCE-DDS: ${DRONE_COUNT} topics from SITL container"
echo "  - WebSocket JSON Bridge: ws://localhost:9090"
echo "  - HTTP API: http://localhost:8000"
echo "  - Mission Executor: Active"
echo ""
echo "Logs:"
echo "  - WS Bridge: /tmp/ws_bridge.log"
echo "  - API: /tmp/api_server.log"
echo "  - Executor: /tmp/mission_executor.log"
echo ""

# 保持运行
wait
