#!/usr/bin/env python3
"""
任务执行器 - 通过PX4 XRCE-DDS话题控制无人机执行航点飞行
"""
import os
import sys
import time
import logging
from typing import Dict
import math

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from px4_msgs.msg import VehicleStatus, VehicleLocalPosition, TrajectorySetpoint, OffboardControlMode, VehicleCommand

logging.basicConfig(level=logging.INFO, format='[EXECUTOR] %(message)s', stream=sys.stdout, force=True)
logger = logging.getLogger(__name__)
sys.stdout.reconfigure(line_buffering=True)

DRONE_COUNT = int(os.environ.get("DRONE_COUNT", "4"))

PX4_QOS = QoSProfile(
    depth=10,
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
)

# VehicleCommand constants
CMD_ARM_DISARM = 400
CMD_SET_MODE = 176
CMD_LAND = 21
ARM_FORCE_MAGIC = 21196.0  # bypass PX4 arming safety checks in SITL

# NAV_STATE values from PX4
NAV_STATE_OFFBOARD = 14
NAV_STATE_AUTO_LOITER = 3
ARMING_STATE_ARMED = 2


def enu_to_ned(x, y, z):
    """ENU (East, North, Up) -> NED (North, East, Down)"""
    return (y, x, -z)


class MissionExecutor(Node):
    """任务执行器节点"""

    def __init__(self):
        super().__init__('mission_executor')
        self.get_logger().info("Mission Executor initializing (XRCE-DDS)...")

        self._db = None
        self._init_db()

        self.drone_states: Dict[int, Dict] = {}
        self.drone_positions: Dict[int, Dict] = {}
        self.active_missions: Dict[int, Dict] = {}
        self._startup_time = time.time()
        self._startup_grace_period = 5.0

        # 发布者缓存
        self._traj_pubs: Dict[int, any] = {}
        self._offboard_pubs: Dict[int, any] = {}
        self._cmd_pubs: Dict[int, any] = {}

        # 订阅每架无人机的状态和位置 (XRCE-DDS topics)
        for i in range(DRONE_COUNT):
            ns = f'/drone_{i}'
            self.create_subscription(
                VehicleStatus, f'{ns}/fmu/out/vehicle_status',
                lambda msg, drone_id=i: self._state_callback(drone_id, msg),
                PX4_QOS
            )
            self.create_subscription(
                VehicleLocalPosition, f'{ns}/fmu/out/vehicle_local_position',
                lambda msg, drone_id=i: self._position_callback(drone_id, msg),
                PX4_QOS
            )
            self.drone_states[i] = {'armed': False, 'mode': 'UNKNOWN', 'connected': False}
            self.drone_positions[i] = {'x': 0.0, 'y': 0.0, 'z': 0.0}

        # OffboardControlMode 心跳 (10Hz, 必须 >= 2Hz)
        self.create_timer(0.1, self._offboard_heartbeat)
        # 任务循环 (1Hz)
        self.create_timer(1.0, self._mission_loop)

        self.get_logger().info(f"Mission Executor ready for {DRONE_COUNT} drones")

    def _init_db(self):
        import pymysql
        self._db = pymysql.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "3306")),
            user=os.environ.get("DB_USER", "root"),
            password=os.environ.get("DB_PASS", "uav123456"),
            database=os.environ.get("DB_NAME", "uav_swarm"),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )

    def _state_callback(self, drone_id: int, msg: VehicleStatus):
        """VehicleStatus -> 内部状态"""
        nav_state_names = {
            0: 'MANUAL', 1: 'ALTCTL', 2: 'POSCTL', 3: 'AUTO_LOITER',
            4: 'AUTO_MISSION', 5: 'AUTO_RTL', 6: 'AUTO_LAND',
            14: 'OFFBOARD', 15: 'STAB',
        }
        self.drone_states[drone_id] = {
            'armed': msg.arming_state == ARMING_STATE_ARMED,
            'mode': nav_state_names.get(msg.nav_state, f'NAV_{msg.nav_state}'),
            'connected': True,
        }

    def _position_callback(self, drone_id: int, msg: VehicleLocalPosition):
        """VehicleLocalPosition is NED (x=North, y=East, z=Down).
        Convert to ENU for internal use to match DB waypoint coordinates."""
        self.drone_positions[drone_id] = {
            'x': msg.y,    # NED East  -> ENU East
            'y': msg.x,    # NED North -> ENU North
            'z': -msg.z,   # NED Down  -> ENU Up
        }

    def _get_or_create_pub(self, drone_id, cache, msg_type, topic_suffix):
        if drone_id not in cache:
            cache[drone_id] = self.create_publisher(
                msg_type,
                f'/drone_{drone_id}/fmu/in/{topic_suffix}',
                PX4_QOS
            )
        return cache[drone_id]

    def _offboard_heartbeat(self):
        """持续发布 OffboardControlMode 心跳以维持 Offboard 模式 (10Hz)"""
        now = int(self.get_clock().now().nanoseconds / 1000)
        for i in range(DRONE_COUNT):
            pub = self._get_or_create_pub(i, self._offboard_pubs, OffboardControlMode, 'offboard_control_mode')
            msg = OffboardControlMode()
            msg.timestamp = now
            msg.position = True
            msg.velocity = False
            msg.acceleration = False
            msg.attitude = False
            msg.body_rate = False
            pub.publish(msg)

    def _publish_vehicle_command(self, drone_id: int, command: int, **params):
        """发布 VehicleCommand 到指定无人机"""
        pub = self._get_or_create_pub(drone_id, self._cmd_pubs, VehicleCommand, 'vehicle_command')
        msg = VehicleCommand()
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        msg.command = command
        msg.param1 = params.get('param1', 0.0)
        msg.param2 = params.get('param2', 0.0)
        msg.param3 = params.get('param3', 0.0)
        msg.param4 = params.get('param4', 0.0)
        msg.param5 = params.get('param5', 0.0)
        msg.param6 = params.get('param6', 0.0)
        msg.param7 = params.get('param7', 0.0)
        msg.target_system = drone_id + 1
        msg.target_component = 0
        msg.source_system = 255
        msg.source_component = 0
        msg.from_external = True
        pub.publish(msg)

    def _mission_loop(self):
        """任务循环：检查数据库中待执行的任务"""
        if time.time() - self._startup_time < self._startup_grace_period:
            return

        try:
            with self._db.cursor() as cur:
                cur.execute("""
                    SELECT m.*, v.vehicle_id
                    FROM mission m
                    JOIN vehicles v ON m.vehicle_id = v.vehicle_id
                    WHERE m.status = 1 AND m.task_name NOT LIKE 'Formation-%%'
                """)
                missions = cur.fetchall()

                for mission in missions:
                    vehicle_id = mission['vehicle_id']
                    mission_id = mission['mission_id']
                    drone_id = vehicle_id - 1

                    if drone_id < 0 or drone_id >= DRONE_COUNT:
                        logger.warning(f"Invalid vehicle_id {vehicle_id} for mission {mission_id}")
                        continue

                    if drone_id not in self.active_missions:
                        self._load_mission(drone_id, mission)

                    self._execute_mission(drone_id)

                # 检查正在执行的任务是否已被用户停止
                for drone_id, data in list(self.active_missions.items()):
                    cur.execute("SELECT status FROM mission WHERE mission_id=%s", (data['mission_id'],))
                    row = cur.fetchone()
                    if not row or row['status'] != 1:
                        logger.info(f"Mission {data['mission_id']} stopped by user, completing...")
                        self._complete_mission(data['mission_id'], success=False)

        except Exception as e:
            logger.error(f"Mission loop error: {e}")

    def _load_mission(self, drone_id: int, mission: Dict):
        mission_id = mission['mission_id']
        with self._db.cursor() as cur:
            cur.execute(
                "SELECT * FROM waypoint WHERE mission_id=%s ORDER BY seq",
                (mission_id,)
            )
            waypoints = cur.fetchall()

        if not waypoints:
            logger.warning(f"Mission {mission_id} has no waypoints, marking completed")
            self._complete_mission(mission_id, success=False)
            return

        self.active_missions[drone_id] = {
            'mission_id': mission_id,
            'task_name': mission['task_name'],
            'waypoints': waypoints,
            'current_wp_index': 0,
            'start_time': time.time(),
            'state': 'init',
        }
        logger.info(f"Loaded mission {mission_id} for drone {drone_id}: {len(waypoints)} waypoints")

    def _execute_mission(self, drone_id: int):
        if drone_id not in self.active_missions:
            return

        mission_data = self.active_missions[drone_id]
        mission_id = mission_data['mission_id']
        waypoints = mission_data['waypoints']
        current_index = mission_data['current_wp_index']
        state = mission_data['state']

        if not self.drone_states[drone_id]['connected']:
            return

        if state == 'init':
            # 持续发送当前位置 setpoint 防止 OFFBOARD failsafe
            pos = self.drone_positions[drone_id]
            self._send_trajectory_setpoint(drone_id, pos['x'], pos['y'], pos['z'])

            # Init timeout: 如果 60s 内无法完成解锁和起飞，标记失败
            init_elapsed = time.time() - mission_data['start_time']
            if init_elapsed > 60:
                logger.error(f"Drone {drone_id} init timeout ({init_elapsed:.0f}s), failing mission")
                mission_data['state'] = 'failed'
                return

            # Step 1: 切换到 OFFBOARD 模式
            if self.drone_states[drone_id]['mode'] != 'OFFBOARD':
                ts = mission_data.setdefault('_mode_ts', 0)
                now = time.time()
                if now - ts > 1.0:
                    logger.info(f"Drone {drone_id} switching to OFFBOARD...")
                    self._publish_vehicle_command(drone_id, CMD_SET_MODE, param1=1.0, param2=6.0)
                    mission_data['_mode_ts'] = now
                return

            # Step 2: 在 OFFBOARD 模式下解锁
            if not self.drone_states[drone_id]['armed']:
                ts = mission_data.setdefault('_arm_ts', 0)
                now = time.time()
                if now - ts > 1.0:
                    logger.info(f"Drone {drone_id} arming in OFFBOARD...")
                    self._publish_vehicle_command(drone_id, CMD_ARM_DISARM, param1=1.0, param2=ARM_FORCE_MAGIC)
                    mission_data['_arm_ts'] = now
                return

            # Step 3: 先飞到第一个航点的高度（takeoff），再水平移动
            if len(waypoints) > 0:
                first_wp = waypoints[0]
                target_z = first_wp['wp_z']
                pos = self.drone_positions[drone_id]
                if abs(pos['z'] - target_z) > 1.0:
                    self._send_trajectory_setpoint(drone_id, pos['x'], pos['y'], target_z)
                    return

            mission_data['state'] = 'flying'
            mission_data['_wp_start'] = time.time()
            logger.info(f"Drone {drone_id} mission {mission_id} started — OFFBOARD mode engaged")

        elif state == 'flying':
            if current_index >= len(waypoints):
                # All waypoints visited, hold at final position before landing
                last_wp = waypoints[-1]
                mission_data['_final_x'] = last_wp['wp_x']
                mission_data['_final_y'] = last_wp['wp_y']
                mission_data['_final_z'] = last_wp['wp_z']
                mission_data['_hold_start'] = time.time()
                mission_data['state'] = 'landing'
                logger.info(f"Drone {drone_id} reached all waypoints, holding at final position...")
                return

            # Per-waypoint timeout: 60s per waypoint
            wp_elapsed = time.time() - mission_data.get('_wp_start', time.time())
            if wp_elapsed > 60:
                logger.warning(f"Drone {drone_id} waypoint {current_index + 1} timeout ({wp_elapsed:.0f}s), skipping")
                mission_data['current_wp_index'] += 1
                mission_data['_wp_start'] = time.time()
                return

            current_wp = waypoints[current_index]
            target_x = current_wp['wp_x']
            target_y = current_wp['wp_y']
            target_z = current_wp['wp_z']

            current_pos = self.drone_positions[drone_id]
            distance = math.sqrt(
                (target_x - current_pos['x'])**2 +
                (target_y - current_pos['y'])**2 +
                (target_z - current_pos['z'])**2
            )

            if distance < 0.5:
                logger.info(f"Drone {drone_id} reached waypoint {current_index + 1}/{len(waypoints)}")
                mission_data['current_wp_index'] += 1
                mission_data['_wp_start'] = time.time()
            else:
                self._send_trajectory_setpoint(drone_id, target_x, target_y, target_z)

        elif state == 'landing':
            # Hold at final position for 3 seconds before landing
            self._send_trajectory_setpoint(drone_id,
                mission_data['_final_x'], mission_data['_final_y'], mission_data['_final_z'])
            if time.time() - mission_data['_hold_start'] > 3.0:
                self._complete_mission(mission_id, success=True)
                logger.info(f"Drone {drone_id} mission {mission_id} completed — landing at target")
                return

        elif state == 'completed':
            self._complete_mission(mission_id, success=True)
            logger.info(f"Drone {drone_id} mission {mission_id} completed")
            return

        elif state == 'failed':
            self._complete_mission(mission_id, success=False)
            logger.error(f"Drone {drone_id} mission {mission_id} failed")
            return

    def _send_trajectory_setpoint(self, drone_id: int, x: float, y: float, z: float):
        """
        发送位置设定点。输入为 ENU 坐标，内部转换为 NED 发布。
        注意: OffboardControlMode 心跳由 _offboard_heartbeat 持续发送。
        """
        pub = self._get_or_create_pub(drone_id, self._traj_pubs, TrajectorySetpoint, 'trajectory_setpoint')
        ned_x, ned_y, ned_z = enu_to_ned(x, y, z)

        msg = TrajectorySetpoint()
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        msg.position = [float(ned_x), float(ned_y), float(ned_z)]
        msg.yaw = float('nan')  # 让 PX4 自行决定航向
        pub.publish(msg)

    def _complete_mission(self, mission_id: int, success: bool):
        status = 2 if success else 3

        # Find the drone associated with this mission and send LAND
        for drone_id, data in list(self.active_missions.items()):
            if data['mission_id'] == mission_id:
                logger.info(f"Drone {drone_id} landing after mission completion...")
                self._publish_vehicle_command(drone_id, CMD_LAND)
                del self.active_missions[drone_id]
                break

        with self._db.cursor() as cur:
            cur.execute(
                "UPDATE mission SET status=%s WHERE mission_id=%s",
                (status, mission_id)
            )
        logger.info(f"Mission {mission_id} marked as {'completed' if success else 'failed'}")


def main():
    rclpy.init()
    executor = MissionExecutor()
    try:
        rclpy.spin(executor)
    except KeyboardInterrupt:
        logger.info("Mission executor shutting down...")
    finally:
        executor.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
