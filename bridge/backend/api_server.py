#!/usr/bin/env python3
"""
UAV Bridge Backend - FastAPI REST API
统一的HTTP API服务器，通过PX4 XRCE-DDS VehicleCommand话题控制无人机
"""
import json
import os
import time
import logging
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

_db = None
DRONE_COUNT = int(os.environ.get("DRONE_COUNT", "4"))

# PX4 VehicleCommand constants
VEHICLE_CMD_ARM_DISARM = 400
VEHICLE_CMD_DO_SET_MODE = 176
VEHICLE_CMD_NAV_TAKEOFF = 22
VEHICLE_CMD_NAV_LAND = 21
VEHICLE_CMD_NAV_RTL = 20

# PX4 custom mode constants
MODE_MAP = {
    'MANUAL':       (1, 0),
    'ALTCTL':       (2, 0),
    'POSCTL':       (3, 0),
    'AUTO.LOITER':  (4, 3),
    'AUTO.RTL':     (4, 4),
    'AUTO.LAND':    (4, 5),
    'AUTO.MISSION': (4, 1),
    'OFFBOARD':     (6, 0),
    'STABILIZED':   (7, 0),
}


# ═══════════════════════════════════════════════════════════
# 数据库连接
# ═══════════════════════════════════════════════════════════

def get_db():
    global _db
    if _db is None:
        import pymysql
        _db = pymysql.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "3306")),
            user=os.environ.get("DB_USER", "root"),
            password=os.environ.get("DB_PASS", "uav123456"),
            database=os.environ.get("DB_NAME", "uav_swarm"),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )
    return _db


# ═══════════════════════════════════════════════════════════
# ROS2 VehicleCommand 发布
# ═══════════════════════════════════════════════════════════

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from px4_msgs.msg import VehicleCommand

PX4_QOS = QoSProfile(
    depth=10,
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
)

_ros_node: Optional[Node] = None
_vehicle_cmd_publishers: Dict[int, any] = {}


def get_ros_node() -> Node:
    global _ros_node
    if _ros_node is None:
        if not rclpy.ok():
            rclpy.init()
        _ros_node = Node('uav_api_server')
        logger.info("ROS2 node initialized (XRCE-DDS mode)")
    return _ros_node


def publish_vehicle_command(drone_id: int, command: int, *,
                            param1: float = 0.0, param2: float = 0.0,
                            param3: float = 0.0, param4: float = 0.0,
                            param5: float = 0.0, param6: float = 0.0,
                            param7: float = 0.0):
    """
    向 /drone_{drone_id}/fmu/in/vehicle_command 发布 VehicleCommand 消息。
    """
    global _vehicle_cmd_publishers
    node = get_ros_node()

    if drone_id not in _vehicle_cmd_publishers:
        _vehicle_cmd_publishers[drone_id] = node.create_publisher(
            VehicleCommand,
            f'/drone_{drone_id}/fmu/in/vehicle_command',
            PX4_QOS
        )

    pub = _vehicle_cmd_publishers[drone_id]
    msg = VehicleCommand()
    msg.timestamp = int(time.time() * 1e6)
    msg.command = command
    msg.param1 = param1
    msg.param2 = param2
    msg.param3 = param3
    msg.param4 = param4
    msg.param5 = param5
    msg.param6 = param6
    msg.param7 = param7
    msg.target_system = drone_id + 1
    msg.target_component = 0
    msg.source_system = 255
    msg.source_component = 0
    msg.from_external = True
    pub.publish(msg)
    time.sleep(0.1)


# ═══════════════════════════════════════════════════════════
# Pydantic 模型
# ═══════════════════════════════════════════════════════════

class Waypoint(BaseModel):
    x: float
    y: float
    z: float = 10.0


class MissionCreate(BaseModel):
    task_name: str
    vehicle_id: int
    waypoints: List[Waypoint] = []
    drone_waypoints: Dict[int, List[Waypoint]] = {}  # vehicle_id -> waypoints (per-drone)


class FormationCreate(BaseModel):
    formation: str  # grid, line, circle
    drones: List[int]
    params: Dict = {}


# ═══════════════════════════════════════════════════════════
# FastAPI 应用
# ═══════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting UAV API Server (XRCE-DDS)...")
    yield
    logger.info("Shutting down UAV API Server...")
    if _ros_node:
        _ros_node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


app = FastAPI(title="SwarmCraft API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


# ═══════════════════════════════════════════════════════════
# 健康检查
# ═══════════════════════════════════════════════════════════

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "drone_count": DRONE_COUNT,
        "ros2_initialized": rclpy.ok() if _ros_node else False,
        "mode": "xrce-dds",
    }


# ═══════════════════════════════════════════════════════════
# 无人机控制 API
# ═══════════════════════════════════════════════════════════

@app.post("/api/drones/{drone_id}/arm")
async def arm_drone(drone_id: int):
    """解锁无人机"""
    try:
        publish_vehicle_command(drone_id, VEHICLE_CMD_ARM_DISARM, param1=1.0)
        return {"drone_id": drone_id, "armed": True, "note": "arm command sent"}
    except Exception as e:
        logger.error(f"Arm drone {drone_id} failed: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/drones/{drone_id}/disarm")
async def disarm_drone(drone_id: int):
    """锁定无人机"""
    try:
        publish_vehicle_command(drone_id, VEHICLE_CMD_ARM_DISARM, param1=0.0)
        return {"drone_id": drone_id, "disarmed": True, "note": "disarm command sent"}
    except Exception as e:
        logger.error(f"Disarm drone {drone_id} failed: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/drones/{drone_id}/takeoff")
async def takeoff_drone(drone_id: int, altitude: float = 5.0):
    """起飞"""
    try:
        lat = float(os.environ.get("PX4_HOME_LAT", "34.23"))
        lon = float(os.environ.get("PX4_HOME_LON", "108.95"))
        publish_vehicle_command(drone_id, VEHICLE_CMD_NAV_TAKEOFF,
                                param5=lat, param6=lon, param7=altitude)
        return {"drone_id": drone_id, "takeoff": True, "altitude": altitude}
    except Exception as e:
        logger.error(f"Takeoff drone {drone_id} failed: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/drones/{drone_id}/land")
async def land_drone(drone_id: int):
    """降落"""
    try:
        publish_vehicle_command(drone_id, VEHICLE_CMD_NAV_LAND)
        return {"drone_id": drone_id, "land": True, "note": "land command sent"}
    except Exception as e:
        logger.error(f"Land drone {drone_id} failed: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/drones/{drone_id}/mode")
async def set_mode(drone_id: int, mode: str = "AUTO.LOITER"):
    """设置飞行模式"""
    try:
        if mode not in MODE_MAP:
            raise HTTPException(400, f"Unknown mode: {mode}. Supported: {list(MODE_MAP.keys())}")

        main_mode, sub_mode = MODE_MAP[mode]
        publish_vehicle_command(drone_id, VEHICLE_CMD_DO_SET_MODE,
                                param1=1.0, param2=float(main_mode), param3=float(sub_mode))
        return {"drone_id": drone_id, "mode": mode, "success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Set mode drone {drone_id} failed: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/drones/{drone_id}/rtl")
async def rtl_drone(drone_id: int):
    """返航"""
    return await set_mode(drone_id, mode="AUTO.RTL")


# ═══════════════════════════════════════════════════════════
# 任务管理 API
# ═══════════════════════════════════════════════════════════

@app.get("/api/missions")
async def list_missions():
    """获取任务列表"""
    db = get_db()
    with db.cursor() as cur:
        cur.execute("""
            SELECT m.*, v.name as vehicle_name
            FROM mission m
            LEFT JOIN vehicles v ON m.vehicle_id = v.vehicle_id
            ORDER BY m.created_at DESC
        """)
        missions = cur.fetchall()

        for mission in missions:
            cur.execute(
                "SELECT * FROM waypoint WHERE mission_id=%s ORDER BY seq",
                (mission['mission_id'],)
            )
            mission['waypoints'] = cur.fetchall()

        return {"missions": missions}


@app.post("/api/missions")
async def create_mission(data: MissionCreate):
    """创建新任务 - vehicle_id 为正数表示单机，负数表示编队(swarm_id)

    - waypoints: 所有无人机共享的航点（per-drone 为空时生效）
    - drone_waypoints: {vehicle_id: [Waypoint, ...]} 每架无人机独立航点
    """
    db = get_db()

    if data.vehicle_id < 0:
        # 编队模式: 为编队内所有无人机创建任务
        swarm_id = -data.vehicle_id
        with db.cursor() as cur:
            cur.execute("SELECT region_json FROM swarm_mission WHERE swarm_id=%s", (swarm_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(400, f"Formation {swarm_id} not found")
            region = json.loads(row['region_json'] or '{}')
            vehicles = region.get('drone_ids', [])
        if not vehicles:
            raise HTTPException(400, f"Formation {swarm_id} has no vehicles")

        mission_ids = []
        for vehicle_id in vehicles:
            # per-drone waypoints take priority, otherwise shared waypoints
            wps = data.drone_waypoints.get(vehicle_id, data.waypoints)
            if not wps:
                raise HTTPException(400, f"No waypoints for vehicle {vehicle_id}")
            target = wps[-1]

            with db.cursor() as cur:
                cur.execute("SELECT vehicle_id FROM vehicles WHERE vehicle_id=%s", (vehicle_id,))
                if not cur.fetchone():
                    cur.execute(
                        "INSERT INTO vehicles (vehicle_id, name, model) VALUES (%s, %s, %s)",
                        (vehicle_id, f"Drone-{vehicle_id:02d}", "gz_x500")
                    )
                cur.execute(
                    """INSERT INTO mission (swarm_id, vehicle_id, task_name, target_x, target_y, target_z, status)
                       VALUES (%s, %s, %s, %s, %s, %s, 0)""",
                    (swarm_id, vehicle_id, data.task_name, target.x, target.y, target.z)
                )
                mission_id = cur.lastrowid
                for i, wp in enumerate(wps):
                    cur.execute(
                        "INSERT INTO waypoint (mission_id, seq, wp_x, wp_y, wp_z) VALUES (%s, %s, %s, %s, %s)",
                        (mission_id, i, wp.x, wp.y, wp.z)
                    )
                mission_ids.append(mission_id)

        logger.info(f"Missions created for formation {swarm_id}: {mission_ids}")
        return {"mission_ids": mission_ids, "swarm_id": swarm_id, "status": "created"}
    else:
        # 单机模式
        waypoints = data.waypoints
        target = waypoints[-1] if waypoints else Waypoint(x=0, y=0, z=10)
        with db.cursor() as cur:
            cur.execute("SELECT vehicle_id FROM vehicles WHERE vehicle_id=%s", (data.vehicle_id,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO vehicles (vehicle_id, name, model) VALUES (%s, %s, %s)",
                    (data.vehicle_id, f"Drone-{data.vehicle_id:02d}", "gz_x500")
                )

            cur.execute(
                """INSERT INTO mission (vehicle_id, task_name, target_x, target_y, target_z, status)
                   VALUES (%s, %s, %s, %s, %s, 0)""",
                (data.vehicle_id, data.task_name, target.x, target.y, target.z)
            )
            mission_id = cur.lastrowid

            for i, wp in enumerate(waypoints):
                cur.execute(
                    "INSERT INTO waypoint (mission_id, seq, wp_x, wp_y, wp_z) VALUES (%s, %s, %s, %s, %s)",
                    (mission_id, i, wp.x, wp.y, wp.z)
                )

        logger.info(f"Mission {mission_id} created: {data.task_name}")
        return {"mission_id": mission_id, "status": "created"}


@app.put("/api/missions/{mission_id}/start")
async def start_mission(mission_id: int):
    """启动任务"""
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM mission WHERE mission_id=%s", (mission_id,))
        mission = cur.fetchone()
        if not mission:
            raise HTTPException(404, "Mission not found")

        cur.execute("UPDATE mission SET status=1 WHERE mission_id=%s", (mission_id,))

    logger.info(f"Mission {mission_id} started")
    return {"mission_id": mission_id, "status": "started"}


@app.put("/api/missions/{mission_id}/stop")
async def stop_mission(mission_id: int):
    """停止任务"""
    db = get_db()
    with db.cursor() as cur:
        cur.execute("UPDATE mission SET status=0 WHERE mission_id=%s", (mission_id,))
    logger.info(f"Mission {mission_id}: stop requested")
    return {"mission_id": mission_id, "status": "stopping"}


@app.delete("/api/missions/{mission_id}")
async def delete_mission(mission_id: int):
    """删除任务"""
    db = get_db()
    with db.cursor() as cur:
        cur.execute("DELETE FROM mission WHERE mission_id=%s", (mission_id,))

    logger.info(f"Mission {mission_id} deleted")
    return {"status": "deleted"}


# ═══════════════════════════════════════════════════════════
# 编队控制 API
# ═══════════════════════════════════════════════════════════

@app.post("/api/swarm/formation")
async def create_formation(data: FormationCreate):
    """创建编队（无人机分组）"""
    db = get_db()
    drone_ids = data.drones
    name = data.params.get("name", f"编队-{len(drone_ids)}架")

    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO swarm_mission (name, drone_count, region_json, status)
               VALUES (%s, %s, %s, 0)""",
            (name, len(drone_ids),
             json.dumps({"drone_ids": drone_ids}))
        )
        swarm_id = cur.lastrowid

        for vehicle_id in drone_ids:
            cur.execute("SELECT vehicle_id FROM vehicles WHERE vehicle_id=%s", (vehicle_id,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO vehicles (vehicle_id, name, model) VALUES (%s, %s, %s)",
                    (vehicle_id, f"Drone-{vehicle_id:02d}", "gz_x500")
                )

    logger.info(f"Swarm {swarm_id} created: {name} with {len(drone_ids)} drones")
    return {
        "swarm_id": swarm_id,
        "name": name,
        "drones": drone_ids,
        "status": "created"
    }


@app.put("/api/swarms/{swarm_id}/start")
async def start_swarm(swarm_id: int):
    """启动编队内所有待执行任务"""
    db = get_db()
    with db.cursor() as cur:
        cur.execute("UPDATE mission SET status=1 WHERE swarm_id=%s AND status=0", (swarm_id,))
        count = cur.rowcount
    if count == 0:
        raise HTTPException(404, "No missions in this formation")
    logger.info(f"Swarm {swarm_id}: {count} missions started")
    return {"swarm_id": swarm_id, "started": count}


@app.put("/api/swarms/{swarm_id}/stop")
async def stop_swarm(swarm_id: int):
    """停止编队内所有正在执行的任务"""
    db = get_db()
    with db.cursor() as cur:
        cur.execute("UPDATE mission SET status=0 WHERE swarm_id=%s AND status=1", (swarm_id,))
        count = cur.rowcount
    logger.info(f"Swarm {swarm_id}: {count} missions stopped")
    return {"swarm_id": swarm_id, "stopped": count}


@app.delete("/api/swarms/{swarm_id}/missions")
async def delete_swarm_missions(swarm_id: int):
    """删除编队下的所有任务（保留编队以便复用）"""
    db = get_db()
    with db.cursor() as cur:
        cur.execute("DELETE FROM mission WHERE swarm_id=%s", (swarm_id,))
        count = cur.rowcount
    logger.info(f"Swarm {swarm_id}: {count} missions deleted (formation kept)")
    return {"swarm_id": swarm_id, "deleted_missions": count}


@app.delete("/api/swarms/{swarm_id}")
async def delete_swarm(swarm_id: int):
    """删除编队及其所有任务"""
    db = get_db()
    with db.cursor() as cur:
        cur.execute("DELETE FROM mission WHERE swarm_id=%s", (swarm_id,))
        cur.execute("DELETE FROM swarm_mission WHERE swarm_id=%s", (swarm_id,))
    logger.info(f"Formation {swarm_id} deleted")
    return {"swarm_id": swarm_id, "status": "deleted"}


@app.get("/api/swarms")
async def list_swarms():
    """列出所有编队"""
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM swarm_mission ORDER BY created_at DESC")
        swarms = cur.fetchall()
    for s in swarms:
        region = json.loads(s['region_json'] or '{}')
        s['vehicle_ids'] = region.get('drone_ids', [])
    return {"swarms": swarms}


# ═══════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
