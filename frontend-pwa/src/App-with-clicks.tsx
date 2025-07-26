// クリック機能付きの地図テスト版
import React, { useState, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './App.css';

// Fix for default markers
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconUrl: '',
  iconRetinaUrl: '',
  shadowUrl: '',
  iconSize: [0, 0],
  shadowSize: [0, 0]
});

// Create custom icons
const startIcon = L.divIcon({
  html: '<div style="background-color: #22c55e; width: 32px; height: 32px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; font-size: 16px;">🚀</div>',
  className: 'custom-marker',
  iconSize: [32, 32],
  iconAnchor: [16, 16]
});

const endIcon = L.divIcon({
  html: '<div style="background-color: #ef4444; width: 32px; height: 32px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; font-size: 16px;">🎯</div>',
  className: 'custom-marker',
  iconSize: [32, 32],
  iconAnchor: [16, 16]
});

// Map click handler component
const MapClickHandler = ({ startPoint, setStartPoint, endPoint, setEndPoint }: {
  startPoint: [number, number] | null;
  setStartPoint: (point: [number, number] | null) => void;
  endPoint: [number, number] | null;
  setEndPoint: (point: [number, number] | null) => void;
}) => {
  const handleMapClick = useCallback((e: any) => {
    const { lat, lng } = e.latlng;
    
    if (!startPoint) {
      setStartPoint([lat, lng]);
      console.log('Start point set:', lat, lng);
    } else if (!endPoint) {
      setEndPoint([lat, lng]);
      console.log('End point set:', lat, lng);
    } else {
      // 両方設定済みの場合は開始点をリセット
      setStartPoint([lat, lng]);
      setEndPoint(null);
      console.log('Reset to new start point:', lat, lng);
    }
  }, [startPoint, endPoint, setStartPoint, setEndPoint]);

  useMapEvents({
    click: handleMapClick
  });

  return null;
};

const App = () => {
  const [startPoint, setStartPoint] = useState<[number, number] | null>(null);
  const [endPoint, setEndPoint] = useState<[number, number] | null>(null);

  return (
    <div className="app-container">
      {/* Map Area - 70-80% of screen */}
      <div className="map-area">
        <MapContainer
          center={[35.6917, 139.7036]} // 新宿駅
          zoom={14}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          />
          
          <MapClickHandler
            startPoint={startPoint}
            setStartPoint={setStartPoint}
            endPoint={endPoint}
            setEndPoint={setEndPoint}
          />
          
          {startPoint && (
            <Marker position={startPoint} icon={startIcon}>
              <Popup>開始地点</Popup>
            </Marker>
          )}
          
          {endPoint && (
            <Marker position={endPoint} icon={endIcon}>
              <Popup>終了地点</Popup>
            </Marker>
          )}
        </MapContainer>

        {/* Map Controls */}
        <div className="map-controls">
          <button className="map-control-btn">
            👁️
          </button>
        </div>
      </div>

      {/* Bottom Sheet */}
      <div className="bottom-sheet peek">
        <div className="bottom-sheet-handle" />
        <div className="bottom-sheet-content">
          <h3>🗺️ クリックテスト</h3>
          <p>地図をクリックして開始・終了地点を設定</p>
          <div style={{ fontSize: '14px', color: '#666' }}>
            {!startPoint && <div>📍 開始地点をタップしてください</div>}
            {startPoint && !endPoint && <div>🎯 終了地点をタップしてください</div>}
            {startPoint && endPoint && <div style={{ color: '#22c55e' }}>✅ 両地点設定完了</div>}
          </div>
        </div>
      </div>

      {/* Bottom Navigation */}
      <nav className="bottom-nav">
        <div className="nav-item active">
          <div className="nav-icon">🗺️</div>
          <div className="nav-label">テスト</div>
        </div>
      </nav>
    </div>
  );
};

export default App;