#!/usr/bin/env python3
"""Minimal ROS2 -> WebSocket bridge using PX4 XRCE-DDS topics."""
import asyncio, json, threading, time, os, math
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from px4_msgs.msg import VehicleStatus, VehicleLocalPosition, BatteryStatus, VehicleAttitude, VehicleGlobalPosition

DRONE_COUNT = int(os.environ.get("DRONE_COUNT", "4"))

# NAV_STATE name lookup (PX4 nav_state integer -> string)
NAV_STATE_NAMES = {
    0: 'MANUAL', 1: 'ALTCTL', 2: 'POSCTL', 3: 'AUTO_LOITER',
    4: 'AUTO_MISSION', 5: 'AUTO_RTL', 6: 'AUTO_LAND',
    7: 'AUTO_RTGS', 8: 'AUTO_READY', 9: 'AUTO_TAKEOFF',
    10: 'ACRO', 11: 'UNUSED', 12: 'DESCEND', 13: 'TERMINATION',
    14: 'OFFBOARD', 15: 'STAB', 16: 'RATTITUDE', 17: 'AUTO_FOLLOW_TARGET',
}

# ── ROS2 Subscriber ──
rclpy.init()
node = Node('ws_bridge')

# PX4 uses BEST_EFFORT reliability
PX4_QOS = QoSProfile(
    depth=10,
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
)

latest = {}
lock = threading.Lock()

def make_cb(d, field):
    def cb(msg):
        data = {}
        if field == 'state':
            data = {
                'armed': msg.arming_state == 2,
                'mode': NAV_STATE_NAMES.get(msg.nav_state, 'UNKNOWN'),
                'connected': True,
            }
        elif field == 'pose':
            # VehicleLocalPosition is NED: x=North, y=East, z=Down
            # Convert to ENU for frontend: x=East, y=North, z=Up
            data = {
                'x': round(msg.y, 4),   # NED East  -> ENU East
                'y': round(msg.x, 4),   # NED North -> ENU North
                'z': round(-msg.z, 4),  # NED Down  -> ENU Up
            }
        elif field == 'battery':
            pct = msg.remaining
            data = {
                'battery': round(pct * 100.0 if pct <= 1.0 else pct, 0),
                'voltage': round(msg.voltage_v, 2) if hasattr(msg, 'voltage_v') else 0.0,
            }
        elif field == 'imu':
            # VehicleAttitude: q = [w, x, y, z] — convert quaternion to yaw (degrees)
            w, x, y, z = msg.q[0], msg.q[1], msg.q[2], msg.q[3]
            yaw = math.degrees(math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))
            data = {'heading': round(yaw, 1)}
        elif field == 'gps':
            data = {'lat': round(msg.lat, 6), 'lon': round(msg.lon, 6), 'alt': round(msg.alt, 2)}
        with lock:
            if d not in latest:
                latest[d] = {'id': d, 'name': f'Drone-{d+1:02d}', 'battery': 100}
            latest[d].update(data)
            latest[d]['last_seen'] = time.time()
    return cb

for i in range(DRONE_COUNT):
    ns = f'/drone_{i}'
    node.create_subscription(VehicleStatus, f'{ns}/fmu/out/vehicle_status', make_cb(i, 'state'), PX4_QOS)
    node.create_subscription(VehicleLocalPosition, f'{ns}/fmu/out/vehicle_local_position', make_cb(i, 'pose'), PX4_QOS)
    node.create_subscription(BatteryStatus, f'{ns}/fmu/out/battery_status', make_cb(i, 'battery'), PX4_QOS)
    node.create_subscription(VehicleAttitude, f'{ns}/fmu/out/vehicle_attitude', make_cb(i, 'imu'), PX4_QOS)
    node.create_subscription(VehicleGlobalPosition, f'{ns}/fmu/out/vehicle_global_position', make_cb(i, 'gps'), PX4_QOS)

print('[WS_BRIDGE] ROS2 subscriptions ready (XRCE-DDS)', flush=True)

# ── WebSocket Server ──
clients = set()

async def ws_handler(websocket):
    clients.add(websocket)
    try:
        async for _ in websocket:
            pass
    finally:
        clients.discard(websocket)

async def broadcast():
    while True:
        if clients:
            with lock:
                # Deep-convert numpy floats/ints to native Python for JSON
                drones_native = {}
                for did, d in latest.items():
                    drones_native[did] = {
                        k: (float(v) if 'float' in str(type(v)) else
                            int(v) if 'int' in str(type(v)) else v)
                        for k, v in d.items()
                    }
                payload = json.dumps({'timestamp': time.time(), 'drones': drones_native})
            dead = set()
            for ws in list(clients):
                try:
                    await ws.send(payload)
                except Exception:
                    dead.add(ws)
            clients.difference_update(dead)
        await asyncio.sleep(0.2)

async def main_async():
    import websockets
    async with websockets.serve(ws_handler, '0.0.0.0', 9090):
        print('[WS_BRIDGE] WebSocket server on :9090', flush=True)
        await broadcast()

def run_asyncio():
    asyncio.run(main_async())

threading.Thread(target=run_asyncio, daemon=True).start()
rclpy.spin(node)
