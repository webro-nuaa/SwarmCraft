export default function DronePanel({ drone, selected, onSelect }) {
  const alt = Number(drone.alt);
  const lat = Number(drone.lat);
  const lon = Number(drone.lon);
  const battery = Number(drone.battery);
  const batteryColor = battery > 50 ? '#4caf50' : battery > 20 ? '#ff9800' : '#f44336';

  return (
    <div className={`drone-panel ${selected ? 'selected' : ''}`} onClick={onSelect}>
      <div className="drone-header">
        <span className={`status-dot ${drone.armed ? 'armed' : 'disarmed'}`} />
        <strong>{drone.name || `Drone-${(drone.id || 0) + 1}`}</strong>
        <span className="mode">{drone.mode || '--'}</span>
      </div>
      <div className="drone-stats">
        <div className="stat">
          <label>高度</label>
          <span>{isNaN(alt) ? '--' : alt.toFixed(1) + 'm'}</span>
        </div>
        <div className="stat">
          <label>位置</label>
          <span>{isNaN(lat) ? '--' : `${lat.toFixed(4)}, ${lon.toFixed(4)}`}</span>
        </div>
        <div className="stat">
          <label>电量</label>
          <span style={{ color: batteryColor }}>{isNaN(battery) ? '--' : battery.toFixed(0) + '%'}</span>
        </div>
        <div className="stat">
          <label>状态</label>
          <span className={drone.armed ? 'armed-text' : ''}>
            {drone.armed ? '已解锁' : '已锁定'}
          </span>
        </div>
      </div>
    </div>
  );
}
