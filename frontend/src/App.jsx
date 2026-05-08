import { useState, useEffect, useCallback } from 'react';
import MapView from './components/MapView';
import DronePanel from './components/DronePanel';
import MissionPlanner from './components/MissionPlanner';
import ControlPanel from './components/ControlPanel';
import './App.css';

// 环境变量配置（支持Docker部署）
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:9090';
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const DRONE_COUNT = parseInt(import.meta.env.VITE_DRONE_COUNT || '4');

export default function App() {
  const [drones, setDrones] = useState({});
  const [selectedDrone, setSelectedDrone] = useState(null);
  const [viewMode, setViewMode] = useState('monitor');
  const [wsStatus, setWsStatus] = useState('connecting');
  const [mapWaypoints, setMapWaypoints] = useState([]);
  const [placingWaypoints, setPlacingWaypoints] = useState(false);
  const [formations, setFormations] = useState([]);

  const loadFormations = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/swarms`);
      const data = await res.json();
      setFormations(data.swarms || []);
    } catch {}
  }, []);

  useEffect(() => { loadFormations(); }, [loadFormations]);

  // GPS → 本地 ENU 转换 (home = 34.23, 108.95)
  const HOME = { lat: 34.23, lon: 108.95 };
  const cosLat = Math.cos(HOME.lat * Math.PI / 180);

  const gpsToEnu = (lat, lon) => {
    const north = (lat - HOME.lat) * 111111.0;
    const east = (lon - HOME.lon) * 111111.0 * cosLat;
    return { x: Math.round(east * 10) / 10, y: Math.round(north * 10) / 10, z: 10 };
  };

  const enuToGps = (x, y) => ({
    lat: HOME.lat + y / 111111.0,
    lon: HOME.lon + x / (111111.0 * cosLat),
  });

  const showMissionWaypoints = useCallback((droneWaypoints) => {
    // Accepts either flat waypoints array (single drone) or [{label, waypoints}] (multi-drone)
    if (!droneWaypoints || droneWaypoints.length === 0) return;
    setPlacingWaypoints(false);

    const groups = Array.isArray(droneWaypoints[0]) || !droneWaypoints[0].waypoints
      ? [{ label: '', waypoints: droneWaypoints }]  // flat array
      : droneWaypoints;  // already grouped [{label, waypoints}]

    const DRONE_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];
    const allWps = [];
    groups.forEach((g, gi) => {
      g.waypoints.forEach(wp => {
        allWps.push({
          ...enuToGps(wp.wp_x, wp.wp_y),
          x: wp.wp_x, y: wp.wp_y, z: wp.wp_z,
          droneLabel: g.label || '',
          color: DRONE_COLORS[gi % DRONE_COLORS.length],
        });
      });
    });
    setMapWaypoints(allWps);
  }, []);

  const handleMapClick = useCallback((lat, lon) => {
    if (!placingWaypoints) return;
    const enu = gpsToEnu(lat, lon);
    setMapWaypoints(prev => [...prev, { lat, lon, ...enu }]);
  }, [placingWaypoints]);

  useEffect(() => {
    let ws = null;
    let reconnectTimer = null;

    const connect = () => {
      try {
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
          console.log('[WS] Connected');
          setWsStatus('connected');
        };

        ws.onclose = () => {
          console.log('[WS] Disconnected, reconnecting in 3s...');
          setWsStatus('disconnected');
          reconnectTimer = setTimeout(connect, 3000);
        };

        ws.onerror = (err) => {
          console.error('[WS] Error:', err);
          setWsStatus('error');
        };

        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data);

            // ws_bridge.py broadcast format: {timestamp, drones: {id: {...}}}
            if (msg.drones) {
              setDrones(prev => {
                const next = { ...prev };
                for (const [idStr, data] of Object.entries(msg.drones)) {
                  const id = parseInt(idStr);
                  next[id] = {
                    ...(prev[id] || {}),
                    ...data,
                    id,
                    name: data.name || prev[id]?.name || `Drone-${id + 1}`,
                  };
                }
                return next;
              });
            }
          } catch (err) {
            console.error('[WS] Parse error:', err);
          }
        };
      } catch (err) {
        console.error('[WS] Connection error:', err);
        setWsStatus('error');
        reconnectTimer = setTimeout(connect, 3000);
      }
    };

    connect();

    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) ws.close();
    };
  }, []);

  const droneList = Object.values(drones);

  const handleDroneSelect = useCallback((id) => {
    setSelectedDrone(id === selectedDrone ? null : id);
  }, [selectedDrone]);

  return (
    <div className="app">
      <header className="topbar">
        <h1>UAV 集群控制系统</h1>
        <nav>
          <button
            className={viewMode === 'monitor' ? 'active' : ''}
            onClick={() => setViewMode('monitor')}
          >
            状态监控
          </button>
          <button
            className={viewMode === 'mission' ? 'active' : ''}
            onClick={() => setViewMode('mission')}
          >
            任务规划
          </button>
          <button
            className={viewMode === 'formation' ? 'active' : ''}
            onClick={() => setViewMode('formation')}
          >
            编队控制
          </button>
        </nav>
        <span className={`ws-status ${wsStatus}`}>
          {wsStatus === 'connected' ? '● 在线' : wsStatus === 'connecting' ? '◌ 连接中' : '○ 离线'}
        </span>
      </header>

      <div className="main">
        <div className="sidebar">
          <div className="drone-list">
            <h3>无人机列表 ({droneList.length})</h3>
            {droneList.map((drone) => (
              <DronePanel
                key={drone.id}
                drone={drone}
                selected={selectedDrone === drone.id}
                onSelect={() => handleDroneSelect(drone.id)}
              />
            ))}
            {droneList.length === 0 && <p className="empty">等待数据...</p>}
          </div>
          <ControlPanel
            drone={droneList.find(d => d.id === selectedDrone)}
            apiUrl={API_URL}
          />
        </div>

        <div className="content">
          <MapView
            drones={droneList}
            selectedDrone={selectedDrone}
            onDroneClick={handleDroneSelect}
            onMapClick={handleMapClick}
            waypoints={mapWaypoints}
          />
          {viewMode === 'mission' && (
            <MissionPlanner
              drones={droneList}
              apiUrl={API_URL}
              mapWaypoints={mapWaypoints}
              onWaypointsChange={setMapWaypoints}
              onPlacingChange={setPlacingWaypoints}
              onShowWaypoints={showMissionWaypoints}
              formations={formations}
            />
          )}
          {viewMode === 'formation' && (
            <FormationPanel
              drones={droneList}
              apiUrl={API_URL}
              formations={formations}
              onFormationCreated={loadFormations}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function FormationPanel({ drones, apiUrl, formations, onFormationCreated }) {
  const [selected, setSelected] = useState([]);
  const [status, setStatus] = useState('');

  const toggleDrone = (id) => {
    setSelected(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const createFormation = async () => {
    try {
      setStatus('创建中...');
      const res = await fetch(`${apiUrl}/api/swarm/formation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          formation: 'group',
          drones: selected.map(id => id + 1),
          params: { name: `编队-${selected.length}架` },
        }),
      });
      const data = await res.json();
      setStatus(`编队已创建 (ID: ${data.swarm_id})`);
      setSelected([]);
      onFormationCreated?.();
      setTimeout(() => setStatus(''), 3000);
    } catch (err) {
      setStatus('创建失败: ' + err.message);
    }
  };

  const deleteFormation = async (swarmId) => {
    if (!confirm(`确定删除编队 #${swarmId}？`)) return;
    try {
      await fetch(`${apiUrl}/api/swarms/${swarmId}`, { method: 'DELETE' });
      onFormationCreated?.();
    } catch (err) {
      alert('删除编队失败: ' + err.message);
    }
  };

  return (
    <div className="panel formation-panel">
      <h3>编队管理</h3>
      <div className="form-group">
        <label>选择无人机加入编队:</label>
        <div className="drone-checkboxes">
          {drones.map(d => (
            <label key={d.id} className="drone-check">
              <input
                type="checkbox"
                checked={selected.includes(d.id)}
                onChange={() => toggleDrone(d.id)}
              />
              {d.name || `Drone-${d.id + 1}`}
              <span className={`status-dot ${d.armed ? 'armed' : ''}`} />
            </label>
          ))}
        </div>
      </div>
      <button
        className="btn primary"
        onClick={createFormation}
        disabled={selected.length < 2}
      >
        创建编队 ({selected.length} 架)
      </button>
      {status && <div className="status-msg">{status}</div>}

      {formations && formations.length > 0 && (
        <div className="mission-list">
          <h4 style={{ fontSize: 13, color: '#9ca3af', marginTop: 16 }}>已有编队</h4>
          {formations.map(f => (
            <div key={f.swarm_id} className="mission-item">
              <div className="mission-info">
                <strong>{f.name || `编队 #${f.swarm_id}`}</strong>
                <span className="mission-meta">
                  {f.drone_count} 架 | 无人机: {f.vehicle_ids?.join(', ')}
                </span>
              </div>
              <div className="mission-actions">
                <button className="btn small danger" onClick={() => deleteFormation(f.swarm_id)}>
                  删除编队
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
