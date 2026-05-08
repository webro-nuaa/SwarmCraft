#!/bin/bash
set -e

DRONE_COUNT=${DRONE_COUNT:-4}
PX4_DIR="/root/PX4-Autopilot"
PX4_BUILD="$PX4_DIR/build/px4_sitl_default"
GAZEBO_SRC="$PX4_DIR/Tools/simulation/gazebo-classic/sitl_gazebo-classic"

cd "$PX4_DIR"

echo "============================================"
echo " PX4 Multi-Drone SITL (XRCE-DDS)"
echo " Drones: ${DRONE_COUNT}"
echo " Agent: UDP :8888"
echo "============================================"

cleanup() {
    echo "[CLEANUP] Shutting down..."
    pkill -9 px4 2>/dev/null || true
    pkill -9 gzserver 2>/dev/null || true
    pkill -9 gzclient 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

# Setup Gazebo environment
source Tools/simulation/gazebo-classic/setup_gazebo.bash "$(pwd)" "$PX4_BUILD" 2>/dev/null || true
export HEADLESS=${HEADLESS:-1}
export PX4_SIM_MODEL=gazebo-classic_iris
export PX4_UXRCE_DDS_PORT=8888
export ROS_DOMAIN_ID=0

# 1. Start Gazebo server
echo "[GAZEBO] Starting gzserver with empty world..."
gzserver --verbose "$GAZEBO_SRC/worlds/empty.world" > /tmp/gzserver.log 2>&1 &
GZSERVER_PID=$!
sleep 5
if ! kill -0 $GZSERVER_PID 2>/dev/null; then
    echo "[ERROR] gzserver failed to start"
    tail -20 /tmp/gzserver.log
    exit 1
fi
echo "[GAZEBO] gzserver running (PID $GZSERVER_PID)"

if [ "$HEADLESS" != "1" ]; then
    echo "[GAZEBO] Starting gzclient for GUI..."
    gzclient > /tmp/gzclient.log 2>&1 &
    GZCLIENT_PID=$!
    echo "[GAZEBO] gzclient running (PID $GZCLIENT_PID)"
fi

# 2. Start PX4 instances and spawn models
echo "[PX4] Starting ${DRONE_COUNT} PX4 instances..."
PX4_BIN="$PX4_BUILD/bin/px4"
PX4_ETC="$PX4_BUILD/etc"
JINJA_GEN="$GAZEBO_SRC/scripts/jinja_gen.py"
MODEL_SDF="$GAZEBO_SRC/models/iris/iris.sdf.jinja"

for i in $(seq 0 $((DRONE_COUNT - 1))); do
    # Start PX4 instance
    PX4_UXRCE_DDS_NS="drone_${i}" \
        PX4_HOME_LAT=${PX4_HOME_LAT:-34.23} \
        PX4_HOME_LON=${PX4_HOME_LON:-108.95} \
        PX4_HOME_ALT=${PX4_HOME_ALT:-488.0} \
        $PX4_BIN -i ${i} -d "$PX4_ETC" -w "sitl_iris_${i}" > /tmp/px4_${i}.log 2>&1 &
    echo "  [PX4] Instance ${i} -> namespace drone_${i} (PID $!)"

    sleep 1

    # Generate SDF model file with per-instance ports
    MAVLINK_TCP=$((4560 + i))
    MAVLINK_UDP=$((14560 + i))
    MAVLINK_ID=$((1 + i))
    GST_UDP=$((5600 + i))

    python3 "$JINJA_GEN" \
        "$MODEL_SDF" \
        "$GAZEBO_SRC" \
        --mavlink_tcp_port $MAVLINK_TCP \
        --mavlink_udp_port $MAVLINK_UDP \
        --mavlink_id $MAVLINK_ID \
        --gst_udp_port $GST_UDP \
        --video_uri $GST_UDP \
        --mavlink_cam_udp_port $((14530 + i)) \
        --output-file "/tmp/iris_${i}.sdf" 2>/dev/null

    # Calculate spawn position: spread drones in a line (3m apart)
    POS_Y=$((i * 3))
    gz model --spawn-file="/tmp/iris_${i}.sdf" --model-name="iris_${i}" \
        -x 0.0 -y $POS_Y -z 0.83 2>/dev/null &
    echo "  [SPAWN] iris_${i} at (0, $POS_Y, 0.83)"

    sleep 2
done

# 3. Wait for all PX4 instances to stabilize
echo "[WAIT] Waiting for all PX4 instances to stabilize..."
sleep 10

# 4. Configure SITL arming parameters
echo "[CONFIG] Setting SITL arming parameters..."
for i in $(seq 0 $((DRONE_COUNT - 1))); do
    for attempt in $(seq 1 30); do
        if $PX4_BUILD/bin/px4-param --instance ${i} set COM_RC_IN_MODE 5 2>/dev/null; then
            break
        fi
        sleep 1
    done
    $PX4_BUILD/bin/px4-param --instance ${i} set NAV_DLL_ACT 0 2>/dev/null || true
    $PX4_BUILD/bin/px4-param --instance ${i} set COM_ARM_WO_GPS 1 2>/dev/null || true
    $PX4_BUILD/bin/px4-param --instance ${i} set CBRK_SUPPLY_CHK 894281 2>/dev/null || true
    $PX4_BUILD/bin/px4-param --instance ${i} set SIM_BAT_MIN_PCT 90 2>/dev/null || true
done
echo "[CONFIG] Arming parameters configured"

echo "============================================"
echo " All ${DRONE_COUNT} drones running"
echo " XRCE-DDS Agent: UDP :8888 (bridge container)"
echo " Namespaces: drone_0 .. drone_$((DRONE_COUNT - 1))"
echo "============================================"

# 5. Monitor
while true; do
    running=$(pgrep -c px4 2>/dev/null || echo 0)
    if [ "$running" -lt "$DRONE_COUNT" ]; then
        echo "[WARN] $(date): Only ${running}/${DRONE_COUNT} px4 processes running"
    fi
    if ! kill -0 $GZSERVER_PID 2>/dev/null; then
        echo "[ERROR] gzserver died, restarting..."
        gzserver --verbose "$GAZEBO_SRC/worlds/empty.world" > /tmp/gzserver.log 2>&1 &
        GZSERVER_PID=$!
    fi
    sleep 10
done
