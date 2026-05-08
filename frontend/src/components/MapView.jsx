import { useEffect, useRef } from 'react';
import L from 'leaflet';

// 无人机圆圈标记
const droneIcon = (armed) => L.divIcon({
  className: 'drone-icon',
  html: `<div class="drone-dot ${armed ? 'armed' : ''}"></div>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

const selectedIcon = (armed) => L.divIcon({
  className: 'drone-icon',
  html: `<div class="drone-dot selected ${armed ? 'armed' : ''}"></div>`,
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

const waypointIcon = (index, color) => L.divIcon({
  className: 'waypoint-icon',
  html: `<div class="waypoint-marker" style="background:${color};border-color:${color}">${index + 1}</div>`,
  iconSize: [24, 24],
  iconAnchor: [12, 12],
});

export default function MapView({ drones, selectedDrone, onDroneClick, onMapClick, waypoints }) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const markersRef = useRef({});
  const wpMarkersRef = useRef([]);
  const wpLinesRef = useRef([]);

  // 初始化地图
  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;
    mapInstance.current = L.map(mapRef.current).setView([34.23, 108.95], 16);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap',
      maxZoom: 20,
    }).addTo(mapInstance.current);

    // 地图点击 → 添加航点
    mapInstance.current.on('click', (e) => {
      if (onMapClick) onMapClick(e.latlng.lat, e.latlng.lng);
    });

    return () => { mapInstance.current?.remove(); mapInstance.current = null; };
  }, []);

  // 点击回调变更时更新
  useEffect(() => {
    const map = mapInstance.current;
    if (!map) return;
    map.off('click');
    map.on('click', (e) => {
      if (onMapClick) onMapClick(e.latlng.lat, e.latlng.lng);
    });
  }, [onMapClick]);

  // 更新无人机标记
  useEffect(() => {
    const map = mapInstance.current;
    if (!map) return;

    drones.forEach((drone) => {
      const lat = drone.lat || 34.23 + Math.random() * 0.01;
      const lon = drone.lon || 108.95 + Math.random() * 0.01;
      const pos = L.latLng(lat, lon);
      const isSelected = drone.id === selectedDrone;

      if (markersRef.current[drone.id]) {
        markersRef.current[drone.id].setLatLng(pos);
        markersRef.current[drone.id].setIcon(droneIcon(drone.armed));
      } else {
        const marker = L.marker(pos, {
          icon: isSelected ? selectedIcon(drone.armed) : droneIcon(drone.armed),
          zIndexOffset: 1000,
        }).addTo(map);
        marker.on('click', (e) => {
          L.DomEvent.stopPropagation(e);
          onDroneClick(drone.id);
        });
        const altVal = Number(drone.alt);
        marker.bindTooltip(`${drone.name || 'Drone-' + (drone.id + 1)} | ${drone.mode} | ${isNaN(altVal) ? 0 : altVal.toFixed(1)}m`, {
          permanent: false, direction: 'top', offset: [0, -20],
        });
        markersRef.current[drone.id] = marker;
      }
    });

    // 清除不存在的无人机
    const currentIds = new Set(drones.map(d => d.id));
    Object.keys(markersRef.current).forEach(id => {
      if (!currentIds.has(Number(id))) {
        map.removeLayer(markersRef.current[id]);
        delete markersRef.current[id];
      }
    });
  }, [drones, selectedDrone, onDroneClick]);

  // 更新航点标记（支持 per-drone 颜色和标签）
  useEffect(() => {
    const map = mapInstance.current;
    if (!map) return;

    // 清除旧标记和线
    wpMarkersRef.current.forEach(m => map.removeLayer(m));
    wpMarkersRef.current = [];
    if (wpLinesRef.current.length) {
      wpLinesRef.current.forEach(l => map.removeLayer(l));
      wpLinesRef.current = [];
    }

    if (!waypoints || waypoints.length === 0) return;

    // 按 drone 分组绘制
    const groups = [];
    let currentLabel = null;
    waypoints.forEach(wp => {
      const label = wp.droneLabel || '';
      if (label !== currentLabel) {
        groups.push({ label, waypoints: [] });
        currentLabel = label;
      }
      groups[groups.length - 1].waypoints.push(wp);
    });

    // 有多个 drone 时重新编号
    let globalIdx = 0;
    groups.forEach(group => {
      const color = group.waypoints[0]?.color || '#ff6600';
      const latlngs = group.waypoints.map((wp, i) => {
        const m = L.marker([wp.lat, wp.lon], { icon: waypointIcon(i, color) }).addTo(map);
        const prefix = group.label ? `${group.label} ` : '';
        m.bindTooltip(`${prefix}航点 ${i + 1}`, { permanent: true, direction: 'top', offset: [0, -12] });
        wpMarkersRef.current.push(m);
        return [wp.lat, wp.lon];
      });

      if (latlngs.length > 1) {
        const line = L.polyline(latlngs, {
          color, weight: 3, opacity: 0.8, dashArray: '10 6',
        }).addTo(map);
        wpLinesRef.current.push(line);
      }
      globalIdx += group.waypoints.length;
    });
  }, [waypoints]);

  // 选中无人机时飞到位置（仅 selection 变化时触发）
  useEffect(() => {
    if (selectedDrone == null) return;
    const drone = drones.find(d => d.id === selectedDrone);
    if (drone && drone.lat && mapInstance.current) {
      mapInstance.current.flyTo([drone.lat, drone.lon], mapInstance.current.getZoom(), { duration: 0.5 });
    }
  }, [selectedDrone]);

  return <div ref={mapRef} className="map-container" />;
}
