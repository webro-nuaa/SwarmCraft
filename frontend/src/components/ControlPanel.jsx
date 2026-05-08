import { useState } from 'react';

export default function ControlPanel({ drone, apiUrl }) {
  const [takeoffAlt, setTakeoffAlt] = useState(5);
  const [status, setStatus] = useState('');

  const call = async (endpoint, method = 'POST') => {
    if (!drone) return;

    setStatus('发送中...');
    try {
      const res = await fetch(`${apiUrl}${endpoint}`, { method });
      const data = await res.json();

      // 显示结果
      if (data.success !== undefined) {
        setStatus(data.success ? '✓ 成功' : '✗ 失败');
      } else if (data.armed !== undefined) {
        setStatus(data.armed ? '✓ 已解锁' : '✗ 解锁失败');
      } else if (data.mode_sent !== undefined) {
        setStatus(data.mode_sent ? '✓ 模式已设置' : '✗ 设置失败');
      } else {
        setStatus('✓ 已发送');
      }

      setTimeout(() => setStatus(''), 3000);
    } catch (e) {
      setStatus('✗ 错误: ' + e.message);
      setTimeout(() => setStatus(''), 5000);
    }
  };

  if (!drone) {
    return (
      <div className="control-panel">
        <h4>操控面板</h4>
        <p className="empty">请先选择一架无人机</p>
      </div>
    );
  }

  return (
    <div className="control-panel">
      <h4>操控 - {drone.name || `Drone-${(drone.id || 0) + 1}`}</h4>

      <div className="drone-status">
        <div className="status-item">
          <span className="label">状态:</span>
          <span className={`value ${drone.armed ? 'armed' : ''}`}>
            {drone.armed ? '已解锁' : '已锁定'}
          </span>
        </div>
        <div className="status-item">
          <span className="label">模式:</span>
          <span className="value">{drone.mode || '--'}</span>
        </div>
        <div className="status-item">
          <span className="label">位置:</span>
          <span className="value">
            X:{(drone.x || 0).toFixed(1)} Y:{(drone.y || 0).toFixed(1)} Z:{(drone.z || 0).toFixed(1)}
          </span>
        </div>
        <div className="status-item">
          <span className="label">电量:</span>
          <span className="value">{drone.battery || 0}%</span>
        </div>
      </div>

      <div className="control-row">
        <button
          className={`btn ctl ${drone.armed ? 'armed' : ''}`}
          onClick={() => call(`/api/drones/${drone.id}/${drone.armed ? 'disarm' : 'arm'}`)}
        >
          {drone.armed ? '🔒 锁定' : '🔓 解锁'}
        </button>
        <button
          className="btn ctl primary"
          onClick={() => call(`/api/drones/${drone.id}/takeoff?altitude=${takeoffAlt}`)}
        >
          ✈️ 起飞
        </button>
      </div>

      <div className="control-row">
        <button
          className="btn ctl"
          onClick={() => call(`/api/drones/${drone.id}/land`)}
        >
          🛬 降落
        </button>
        <button
          className="btn ctl"
          onClick={() => call(`/api/drones/${drone.id}/rtl`)}
        >
          🏠 返航
        </button>
      </div>

      <div className="control-row">
        <button
          className="btn ctl"
          onClick={() => call(`/api/drones/${drone.id}/mode?mode=AUTO.LOITER`)}
        >
          悬停
        </button>
        <button
          className="btn ctl"
          onClick={() => call(`/api/drones/${drone.id}/mode?mode=AUTO.MISSION`)}
        >
          任务模式
        </button>
      </div>

      <div className="form-group">
        <label>起飞高度 (m):</label>
        <input
          type="number"
          value={takeoffAlt}
          min={1}
          max={100}
          step={1}
          onChange={e => setTakeoffAlt(Number(e.target.value))}
        />
      </div>

      {status && <div className="control-status">{status}</div>}
    </div>
  );
}
