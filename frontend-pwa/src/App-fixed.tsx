// 修正版App - 動作するテスト版をベースに必要機能のみ追加
import React, { useState, useCallback, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, Polygon, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './App.css';
import './map-icons.css';

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
    return 'http://localhost:8001';
  }
  
  // その他の場合（外部IPアクセス）は同じホストのポート8001を使用
  return `http://${hostname}:8001`;
};

const API_BASE_URL = getApiBaseUrl();

// Map click handler component
const MapClickHandler = ({ 
  startPoint, 
  setStartPoint, 
  endPoint, 
  setEndPoint, 
  setRoute, 
  setRouteInfo,
  customNodeMode,
  onAddCustomNode 
}: {
  startPoint: [number, number] | null;
  setStartPoint: (point: [number, number] | null) => void;
  endPoint: [number, number] | null;
  setEndPoint: (point: [number, number] | null) => void;
  setRoute: (route: RoutePoint[]) => void;
  setRouteInfo: (info: RouteInfo | null) => void;
  customNodeMode: boolean;
  onAddCustomNode: (lat: number, lng: number) => void;
}) => {
  const handleMapClick = useCallback((e: any) => {
    const { lat, lng } = e.latlng;
    
    if (customNodeMode) {
      onAddCustomNode(lat, lng);
      return;
    }
    
    if (!startPoint) {
      setStartPoint([lat, lng]);
      setRoute([]);
      setRouteInfo(null);
      console.log('Start point set:', lat, lng);
    } else if (!endPoint) {
      setEndPoint([lat, lng]);
      setRoute([]);
      setRouteInfo(null);
      console.log('End point set:', lat, lng);
    } else {
      // 両方設定済みの場合は開始点をリセット
      setStartPoint([lat, lng]);
      setEndPoint(null);
      setRoute([]);
      setRouteInfo(null);
      console.log('Reset to new start point:', lat, lng);
    }
  }, [startPoint, endPoint, setStartPoint, setEndPoint, setRoute, setRouteInfo, customNodeMode, onAddCustomNode]);

  useMapEvents({
    click: handleMapClick
  });

  return null;
};

const App = () => {
  // 状態管理
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

  // ルート計算
  const calculateRoute = useCallback(async () => {
    if (!startPoint || !endPoint) {
      alert('開始地点と終了地点を設定してください');
      return;
    }

    setLoading(true);
    setComparison(null);
    
    try {
      const now = new Date();
      const time = selectedTime || `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
      const date = now.toISOString().split('T')[0];

      const requestData = {
        start: [startPoint[1], startPoint[0]], // lng, lat
        end: [endPoint[1], endPoint[0]], // lng, lat
        time,
        date,
        transport_mode: transportMode
      };
      
      const endpoint = usesDijkstra ? '/api/route/dijkstra' : '/api/route/shade-avoid';
      console.log('Sending request to:', `${API_BASE_URL}${endpoint}`);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000); // 2分

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestData),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (response.ok) {
        const data = await response.json();
        console.log('Route data received:', data);
        setRoute(data.route_points || []);
        setRouteInfo(data);
        setUsesDijkstra(data.uses_dijkstra || false);
      } else {
        console.error('Failed to calculate route:', response.status);
        alert('ルート計算に失敗しました');
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.warn('Route calculation timeout');
        alert('ルート計算がタイムアウトしました');
      } else {
        console.error('Error calculating route:', error);
        alert('ルート計算エラーが発生しました');
      }
    } finally {
      setLoading(false);
    }
  }, [startPoint, endPoint, selectedTime, transportMode, usesDijkstra]);

  // ダミーのカスタムノード追加関数
  const onAddCustomNode = useCallback((lat: number, lng: number) => {
    console.log('Custom node add request:', lat, lng);
    // 実装は後で追加
  }, []);

  // 初期化
  useEffect(() => {
    // 現在時刻を設定
    const now = new Date();
    setSelectedTime(`${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`);
  }, []);

  // ルートポイントをLeafletのLatLng形式に変換
  const routeLatLngs = route.map(point => [point.latitude, point.longitude] as [number, number]);

  return (
    <div className="app-container">
      {/* Map Area */}
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
            setRoute={setRoute}
            setRouteInfo={setRouteInfo}
            customNodeMode={customNodeMode}
            onAddCustomNode={onAddCustomNode}
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

          {routeLatLngs.length > 0 && (
            <Polyline 
              positions={routeLatLngs} 
              color="#ef4444" 
              weight={4} 
              opacity={0.8}
            />
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
          <h3>🗺️ 日陰ルート</h3>
          
          <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
            <button 
              onClick={calculateRoute}
              disabled={!startPoint || !endPoint || loading}
              style={{
                flex: 1,
                padding: '12px',
                backgroundColor: loading ? '#ccc' : 'var(--primary-cool)',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                cursor: loading ? 'not-allowed' : 'pointer'
              }}
            >
              {loading ? '計算中...' : '🔍 ルート検索'}
            </button>
            
            <button 
              onClick={() => {
                setStartPoint(null);
                setEndPoint(null);
                setRoute([]);
                setRouteInfo(null);
              }}
              style={{
                padding: '12px 16px',
                backgroundColor: '#6c757d',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                cursor: 'pointer'
              }}
            >
              🗑️
            </button>
          </div>

          {routeInfo && (
            <div style={{ background: '#f5f5f5', padding: '16px', borderRadius: '8px' }}>
              <h4>ルート情報</h4>
              <div>📏 距離: {Math.round(routeInfo.total_distance)}m</div>
              <div>⏱️ 時間: {routeInfo.estimated_time}分</div>
              <div>🌳 日陰率: {Math.round(routeInfo.average_shade_ratio * 100)}%</div>
            </div>
          )}

          <div style={{ fontSize: '14px', color: '#666', marginTop: '12px' }}>
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