// モバイルCSS付きの地図テスト版
import React from 'react';
import { MapContainer, TileLayer } from 'react-leaflet';
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

const App = () => {
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
          <h3>🗺️ モバイルCSS テスト</h3>
          <p>ボトムシートが表示されているか確認</p>
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