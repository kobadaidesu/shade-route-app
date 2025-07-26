// 複雑なstate管理付きテスト版
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

// インターフェース定義
interface RoutePoint {
  longitude: number;
  latitude: number;
  shade_ratio: number;
}

interface RouteInfo {
  route_points: RoutePoint[];
  total_distance: number;
  estimated_time: number;
  average_shade_ratio: number;
  transport_mode: string;
  area_name: string;
  cache_used?: boolean;
  calculation_time_ms?: number;
  weather_condition?: string;
}

interface Building {
  type: string;
  geometry: {
    type: string;
    coordinates: number[][][];
  };
  properties: {
    building: string;
    height: number;
    osm_id: number;
  };
}

interface CustomNode {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
  node_type: string;
  description?: string;
  created_by: string;
  created_at: string;
  icon_type: string;
  color?: string;
}

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

// 動的にAPI URLを設定（スマホアクセス対応）
const getApiBaseUrl = () => {
  // 環境変数が設定されている場合はそれを使用
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }
  
  // 現在のホスト名を取得
  const hostname = window.location.hostname;
  
  // localhost または 127.0.0.1 の場合はlocalhostを使用
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'http://localhost:8006';
  }
  
  // その他の場合（外部IPアクセス）は同じホストのポート8006を使用
  return `http://${hostname}:8006`;
};

const API_BASE_URL = getApiBaseUrl();

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
  // 状態管理（元のApp.tsxから）
  const [startPoint, setStartPoint] = useState<[number, number] | null>(null);
  const [endPoint, setEndPoint] = useState<[number, number] | null>(null);
  const [route, setRoute] = useState<RoutePoint[]>([]);
  const [routeInfo, setRouteInfo] = useState<RouteInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [transportMode, setTransportMode] = useState('walk');
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [usesDijkstra, setUsesDijkstra] = useState(false);
  const [comparison, setComparison] = useState<any>(null);
  const [selectedTime, setSelectedTime] = useState('');
  const [autoUpdate, setAutoUpdate] = useState(false);
  const [hideOSMIcons, setHideOSMIcons] = useState(true);
  const [customNodes, setCustomNodes] = useState<CustomNode[]>([]);
  const [customNodeMode, setCustomNodeMode] = useState(false);

  // UI状態
  const [bottomSheetState, setBottomSheetState] = useState<'collapsed' | 'peek' | 'expanded'>('peek');
  const [activeTab, setActiveTab] = useState<'route' | 'nodes' | 'settings'>('route');

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
      <div className={`bottom-sheet ${bottomSheetState}`}>
        <div className="bottom-sheet-handle" />
        <div className="bottom-sheet-content">
          <h3>🗺️ 複雑State テスト</h3>
          <p>Loading: {loading ? 'Yes' : 'No'}</p>
          <p>Transport: {transportMode}</p>
          <p>Buildings: {buildings.length}</p>
          <p>Custom Nodes: {customNodes.length}</p>
          <div style={{ fontSize: '14px', color: '#666' }}>
            {!startPoint && <div>📍 開始地点をタップしてください</div>}
            {startPoint && !endPoint && <div>🎯 終了地点をタップしてください</div>}
            {startPoint && endPoint && <div style={{ color: '#22c55e' }}>✅ 両地点設定完了</div>}
          </div>
        </div>
      </div>

      {/* Bottom Navigation */}
      <nav className="bottom-nav">
        <div className={`nav-item ${activeTab === 'route' ? 'active' : ''}`}>
          <div className="nav-icon">🗺️</div>
          <div className="nav-label">ルート</div>
        </div>
        <div className={`nav-item ${activeTab === 'nodes' ? 'active' : ''}`}>
          <div className="nav-icon">📍</div>
          <div className="nav-label">ノード</div>
        </div>
        <div className={`nav-item ${activeTab === 'settings' ? 'active' : ''}`}>
          <div className="nav-icon">⚙️</div>
          <div className="nav-label">設定</div>
        </div>
      </nav>
    </div>
  );
};

export default App;