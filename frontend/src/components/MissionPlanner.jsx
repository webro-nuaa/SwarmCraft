import { useState, useEffect } from 'react';

export default function MissionPlanner({ drones, apiUrl, mapWaypoints, onWaypointsChange, onPlacingChange, onShowWaypoints, formations }) {
  const [missions, setMissions] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [taskName, setTaskName] = useState('');
  const [vehicleId, setVehicleId] = useState(1);
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  // Formation mode: 'shared' = same waypoints for all, 'per-drone' = each drone own waypoints
  const [formationMode, setFormationMode] = useState('shared');
  const [droneTabs, setDroneTabs] = useState([]);
  const [activeTabIdx, setActiveTabIdx] = useState(0);
  const [perDroneWps, setPerDroneWps] = useState({});

  const loadMissions = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${apiUrl}/api/missions`);
      const data = await res.json();
      setMissions(data.missions || []);
    } catch (err) {
      console.error('Load missions failed:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMissions();
    const interval = setInterval(loadMissions, 5000);
    return () => clearInterval(interval);
  }, [apiUrl]);

  // When vehicleId changes or mode toggles, init/reset waypoints
  useEffect(() => {
    if (vehicleId < 0 && formations.length > 0) {
      const swarmId = -vehicleId;
      const f = formations.find(x => x.swarm_id === swarmId);
      if (f && f.vehicle_ids && f.vehicle_ids.length > 0) {
        const vids = f.vehicle_ids.sort((a, b) => a - b);
        if (formationMode === 'per-drone') {
          const tabs = vids.map(vid => ({
            vehicle_id: vid,
            label: `Drone-${String(vid).padStart(2, '0')}`,
          }));
          setDroneTabs(tabs);
          setActiveTabIdx(0);
          const map = {};
          vids.forEach(v => { map[v] = perDroneWps[v] || []; });
          setPerDroneWps(map);
          onWaypointsChange(map[vids[0]] || []);
        } else {
          // shared mode: single waypoint list for all
          setDroneTabs([]);
          setPerDroneWps({});
          onWaypointsChange([]);
        }
      }
    } else {
      setDroneTabs([]);
      setPerDroneWps({});
    }
  }, [vehicleId, formationMode]);

  const switchDroneTab = (idx) => {
    // Save current tab's waypoints before switching
    const prevVid = droneTabs[activeTabIdx]?.vehicle_id;
    if (prevVid != null) {
      setPerDroneWps(prev => ({ ...prev, [prevVid]: mapWaypoints }));
    }
    // Load new tab's waypoints
    const nextVid = droneTabs[idx]?.vehicle_id;
    setActiveTabIdx(idx);
    onWaypointsChange(perDroneWps[nextVid] || []);
  };

  const openForm = () => {
    setShowForm(true);
    onPlacingChange(true);
    onWaypointsChange([]);
    setTaskName('');
    setPerDroneWps({});
    setDroneTabs([]);
    setFormationMode('shared');
    setStatusMsg('在地图上点击添加航点...');
  };

  const closeForm = () => {
    setShowForm(false);
    onPlacingChange(false);
    onWaypointsChange([]);
    setStatusMsg('');
    setDroneTabs([]);
    setPerDroneWps({});
  };

  const removeWaypoint = (i) => {
    onWaypointsChange(prev => prev.filter((_, idx) => idx !== i));
  };

  const createMission = async () => {
    if (!taskName.trim()) {
      setStatusMsg('请输入任务名称');
      return;
    }
    if (vehicleId < 0) {
      // Formation mode
      try {
        setLoading(true);
        setStatusMsg('创建中...');
        let body;
        if (formationMode === 'per-drone') {
          // Per-drone: save current tab's waypoints first
          const currentVid = droneTabs[activeTabIdx]?.vehicle_id;
          if (currentVid != null) {
            setPerDroneWps(prev => ({ ...prev, [currentVid]: mapWaypoints }));
          }
          const finalMap = { ...perDroneWps };
          if (currentVid != null) finalMap[currentVid] = mapWaypoints;
          const emptyDrone = droneTabs.find(t => !finalMap[t.vehicle_id] || finalMap[t.vehicle_id].length === 0);
          if (emptyDrone) {
            setStatusMsg(`${emptyDrone.label} 还没有航点，请点击标签添加`);
            setLoading(false);
            return;
          }
          body = { task_name: taskName, vehicle_id: vehicleId, waypoints: [], drone_waypoints: finalMap };
        } else {
          // Shared: same waypoints for all drones
          if (mapWaypoints.length === 0) {
            setStatusMsg('请在地图上至少点击添加一个航点');
            setLoading(false);
            return;
          }
          body = { task_name: taskName, vehicle_id: vehicleId, waypoints: mapWaypoints.map(wp => ({ x: wp.x, y: wp.y, z: wp.z })) };
        }
        const res = await fetch(`${apiUrl}/api/missions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        closeForm();
        await loadMissions();
      } catch (err) {
        setStatusMsg('创建失败: ' + err.message);
      } finally {
        setLoading(false);
      }
    } else {
      // Single drone mode
      if (mapWaypoints.length === 0) {
        setStatusMsg('请在地图上至少点击添加一个航点');
        return;
      }
      try {
        setLoading(true);
        setStatusMsg('创建中...');
        const body = {
          task_name: taskName,
          vehicle_id: vehicleId,
          waypoints: mapWaypoints.map(wp => ({ x: wp.x, y: wp.y, z: wp.z })),
        };
        const res = await fetch(`${apiUrl}/api/missions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        closeForm();
        await loadMissions();
      } catch (err) {
        setStatusMsg('创建失败: ' + err.message);
      } finally {
        setLoading(false);
      }
    }
  };

  const startMission = async (id) => {
    try {
      const res = await fetch(`${apiUrl}/api/missions/${id}/start`, { method: 'PUT' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadMissions();
    } catch (err) {
      alert('启动任务失败: ' + err.message);
    }
  };

  const stopMission = async (missionId) => {
    try {
      const res = await fetch(`${apiUrl}/api/missions/${missionId}/stop`, { method: 'PUT' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadMissions();
    } catch (err) {
      alert('停止任务失败: ' + err.message);
    }
  };

  const deleteMission = async (id) => {
    if (!confirm('确定删除此任务？')) return;
    try {
      await fetch(`${apiUrl}/api/missions/${id}`, { method: 'DELETE' });
      await loadMissions();
    } catch (err) {
      alert('删除任务失败: ' + err.message);
    }
  };

  const getStatusText = (status) => {
    const map = { 0: '待执行', 1: '执行中', 2: '已完成', 3: '失败' };
    return map[status] || '未知';
  };

  const getStatusClass = (status) => {
    const map = { 0: 'pending', 1: 'running', 2: 'completed', 3: 'failed' };
    return map[status] || 'unknown';
  };

  const visibleMissions = missions.filter(m => !(m.task_name && m.task_name.startsWith('Formation-')));

  // 将同一批次（同 swarm_id + task_name）的子任务合并为一个任务显示
  const mergedMissions = () => {
    const groups = [];
    const seen = new Set();
    for (const m of visibleMissions) {
      const key = m.swarm_id ? `swarm|${m.swarm_id}|${m.task_name}` : `single|${m.mission_id}`;
      if (m.swarm_id) {
        if (seen.has(key)) continue;
        seen.add(key);
        const batch = visibleMissions.filter(x => x.swarm_id === m.swarm_id && x.task_name === m.task_name);
        const anyPending = batch.some(x => x.status === 0);
        const anyRunning = batch.some(x => x.status === 1);
        const anyFailed = batch.some(x => x.status === 3);
        const allDone = batch.every(x => x.status >= 2);
        groups.push({
          key,
          task_name: m.task_name,
          swarm_id: m.swarm_id,
          missions: batch,
          droneCount: batch.length,
          totalWps: batch.reduce((s, x) => s + (x.waypoints?.length || 0), 0),
          status: anyRunning ? 1 : anyPending ? 0 : anyFailed ? 3 : allDone ? 2 : 0,
        });
      } else {
        groups.push({
          key,
          task_name: m.task_name,
          swarm_id: null,
          missions: [m],
          droneCount: 1,
          totalWps: m.waypoints?.length || 0,
          status: m.status,
        });
      }
    }
    return groups;
  };

  // Compute total waypoints in per-drone mode
  const totalWps = vehicleId < 0 && formationMode === 'per-drone'
    ? Object.values(perDroneWps).reduce((sum, wps) => sum + wps.length, 0)
    : mapWaypoints.length;

  const saveDisabled = !taskName.trim() || loading
    || (vehicleId < 0 && formationMode === 'per-drone' ? totalWps === 0 : mapWaypoints.length === 0);

  const saveLabel = () => {
    if (vehicleId < 0 && formationMode === 'per-drone') {
      return `保存任务 (${droneTabs.length} 架/${totalWps} 航点)`;
    }
    return `保存任务 (${mapWaypoints.length} 航点)`;
  };

  return (
    <div className="mission-panel panel">
      <div className="panel-header">
        <h3>任务规划</h3>
        {!showForm ? (
          <button className="btn primary" onClick={openForm} disabled={loading}>
            新建任务
          </button>
        ) : (
          <button className="btn" onClick={closeForm}>取消</button>
        )}
        <button className="btn" onClick={loadMissions} disabled={loading}>
          {loading ? '刷新中...' : '刷新'}
        </button>
        {!showForm && mapWaypoints.length > 0 && (
          <button className="btn" onClick={() => onWaypointsChange([])}>清除显示</button>
        )}
      </div>

      {showForm && (
        <div className="mission-form">
          <div className="form-group">
            <label>任务名称</label>
            <input
              value={taskName}
              onChange={e => setTaskName(e.target.value)}
              placeholder="输入任务名称"
            />
          </div>
          <div className="form-group">
            <label>执行无人机</label>
            <select value={vehicleId} onChange={e => setVehicleId(parseInt(e.target.value))}>
              <optgroup label="单机">
                {drones.map(d => (
                  <option key={`d${d.id}`} value={d.id + 1}>
                    {d.name || `Drone-${d.id + 1}`}
                    {d.armed ? ' (已解锁)' : ' (已锁定)'}
                  </option>
                ))}
                {drones.length === 0 && <option value={1}>Drone-01</option>}
              </optgroup>
              {formations && formations.length > 0 && (
                <optgroup label="编队">
                  {formations.filter(f => f.vehicle_ids && f.vehicle_ids.length > 0).map(f => (
                    <option key={`f${f.swarm_id}`} value={-f.swarm_id}>
                      {f.name || `编队 #${f.swarm_id}`} ({f.drone_count} 架)
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
          </div>

          {/* Mode toggle when formation selected */}
          {vehicleId < 0 && (
            <div className="form-group">
              <label>航点模式:</label>
              <div className="mode-toggle">
                <button
                  className={`toggle-btn ${formationMode === 'shared' ? 'active' : ''}`}
                  onClick={() => setFormationMode('shared')}
                >
                  共享航点
                </button>
                <button
                  className={`toggle-btn ${formationMode === 'per-drone' ? 'active' : ''}`}
                  onClick={() => setFormationMode('per-drone')}
                >
                  分派航点
                </button>
              </div>
              <span style={{ fontSize: 11, color: '#6b7280', marginTop: 4, display: 'block' }}>
                {formationMode === 'shared'
                  ? '所有无人机执行相同航点序列'
                  : '为每架无人机分别指定航点'}
              </span>
            </div>
          )}

          {/* Per-drone tabs for formation missions */}
          {droneTabs.length > 0 && (
            <div className="drone-tabs">
              <label>为每架无人机分配航点:</label>
              <div className="tabs-row">
                {droneTabs.map((tab, idx) => {
                  const wpCount = idx === activeTabIdx
                    ? mapWaypoints.length
                    : (perDroneWps[tab.vehicle_id] || []).length;
                  return (
                    <button
                      key={tab.vehicle_id}
                      className={`tab-btn ${idx === activeTabIdx ? 'active' : ''}`}
                      onClick={() => switchDroneTab(idx)}
                    >
                      {tab.label}
                      {wpCount > 0 && <span className="wp-badge">{wpCount}</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div className="waypoints-list">
            <label>
              {droneTabs.length > 0
                ? `${droneTabs[activeTabIdx]?.label} 航点 (在地图上点击添加):`
                : '航点序列 (在地图上点击添加):'}
            </label>
            {mapWaypoints.length === 0 && (
              <p className="hint">← 请在地图上点击添加航点，航点将自动按点击顺序连接</p>
            )}
            {mapWaypoints.map((wp, i) => (
              <div key={i} className="waypoint-row">
                <span className="wp-num">#{i + 1}</span>
                <span className="wp-coord">E: {wp.x.toFixed(1)}m</span>
                <span className="wp-coord">N: {wp.y.toFixed(1)}m</span>
                <span className="wp-coord">U: {wp.z.toFixed(0)}m</span>
                <span className="wp-gps">({wp.lat.toFixed(6)}, {wp.lon.toFixed(6)})</span>
                <button className="btn small danger" onClick={() => removeWaypoint(i)}>×</button>
              </div>
            ))}
            {mapWaypoints.length > 0 && (
              <button className="btn small" onClick={() => onWaypointsChange([])}>
                清空当前航点
              </button>
            )}
          </div>

          <button
            className="btn primary"
            onClick={createMission}
            disabled={saveDisabled}
          >
            {saveLabel()}
          </button>
          {statusMsg && <div className="status-msg">{statusMsg}</div>}
        </div>
      )}

      <div className="mission-list">
        {loading && visibleMissions.length === 0 && <p className="empty">加载中...</p>}
        {!loading && visibleMissions.length === 0 && <p className="empty">暂无任务，点击"新建任务"开始规划</p>}

        {mergedMissions().map(g => (
          <div key={g.key} className="mission-item">
            <div className="mission-info">
              <strong>{g.task_name}</strong>
              <span className="mission-meta">
                {g.swarm_id
                  ? `编队 #${g.swarm_id} · ${g.droneCount} 架无人机 · ${g.totalWps} 个航点`
                  : `${g.missions[0].vehicle_name || `Drone-${String(g.missions[0].vehicle_id).padStart(2, '0')}`} · ${g.totalWps} 个航点`
                }
              </span>
              <span className={`status-tag status-${getStatusClass(g.status)}`}>
                {getStatusText(g.status)}
              </span>
            </div>
            <div className="mission-actions">
              <button
                className="btn small"
                onClick={() => {
                  const allWps = g.missions.map(m => ({
                    label: m.vehicle_name || `Drone-${String(m.vehicle_id).padStart(2, '0')}`,
                    waypoints: m.waypoints || [],
                  }));
                  onShowWaypoints(allWps.length === 1 && !allWps[0].label ? allWps[0].waypoints : allWps);
                }}
              >
                显示航点
              </button>
              {g.status === 0 && (
                <button className="btn small primary" onClick={() => {
                  if (g.swarm_id) {
                    fetch(`${apiUrl}/api/swarms/${g.swarm_id}/start`, { method: 'PUT' }).then(loadMissions);
                  } else {
                    startMission(g.missions[0].mission_id);
                  }
                }}>
                  启动
                </button>
              )}
              {g.status === 1 && (
                <button className="btn small warning" onClick={() => {
                  if (g.swarm_id) {
                    fetch(`${apiUrl}/api/swarms/${g.swarm_id}/stop`, { method: 'PUT' }).then(loadMissions);
                  } else {
                    stopMission(g.missions[0].mission_id);
                  }
                }}>
                  停止
                </button>
              )}
              {g.status !== 1 && (
                <button className="btn small danger" onClick={() => {
                  if (g.swarm_id) {
                    if (!confirm(`确定删除任务"${g.task_name}"？`)) return;
                    Promise.all(g.missions.map(m =>
                      fetch(`${apiUrl}/api/missions/${m.mission_id}`, { method: 'DELETE' })
                    )).then(loadMissions);
                  } else {
                    deleteMission(g.missions[0].mission_id);
                  }
                }}>
                  删除
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
