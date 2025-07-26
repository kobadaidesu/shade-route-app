import { useState, useEffect, useCallback, useMemo, memo } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, Polygon, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './App.css';
import './map-icons.css';

// Fix for default markers - クリーンなマップのため無効化
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

// カスタムアイコン作成関数
const createCustomNodeIcon = (emoji: string, color: string = '#ff4444') => {
  return L.divIcon({
    className: 'custom-node-icon',
    html: `
      <div style="
        background: ${color};
        border: 2px solid white;
        border-radius: 50%;
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 16px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.3);
      ">${emoji}</div>
    `,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
    popupAnchor: [0, -16]
  });
};

// ハプティックフィードバック
const triggerHaptic = () => {
  if ('vibrate' in navigator) {
    navigator.vibrate(50);
  }
};

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

// デバッグ用：API URLをコンソールに出力
console.log('🔗 API_BASE_URL:', API_BASE_URL);

// Map click handler component
interface MapClickEvent {
  latlng: {
    lat: number;
    lng: number;
  };
}

const MapClickHandler = memo(({ 
  startPoint, 
  endPoint, 
  setStartPoint, 
  setEndPoint, 
  setRoute, 
  setRouteInfo,
  onMapUpdate,
  customNodeMode,
  onAddCustomNode
}: {
  startPoint: [number, number] | null;
  endPoint: [number, number] | null;
  setStartPoint: (point: [number, number] | null) => void;
  setEndPoint: (point: [number, number] | null) => void;
  setRoute: (route: RoutePoint[]) => void;
  setRouteInfo: (info: RouteInfo | null) => void;
  onMapUpdate: () => void;
  customNodeMode: boolean;
  onAddCustomNode: (lat: number, lng: number) => void;
}) => {
  const handleMapClick = useCallback((e: MapClickEvent) => {
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
    click: handleMapClick,
    moveend: onMapUpdate,
    zoomend: onMapUpdate
  });

  return null;
});

function App() {
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

  // アイコンオプション
  const iconOptions = [
    { emoji: '📍', name: 'デフォルト' },
    { emoji: '🏠', name: '家' },
    { emoji: '🏢', name: 'オフィス' },
    { emoji: '🏪', name: '店舗' },
    { emoji: '🍽️', name: 'レストラン' },
    { emoji: '☕', name: 'カフェ' },
    { emoji: '🚉', name: '駅' },
    { emoji: '🚌', name: 'バス停' },
    { emoji: '🏥', name: '病院' },
    { emoji: '🏫', name: '学校' },
    { emoji: '🏛️', name: '公共施設' },
    { emoji: '🌳', name: '公園' },
    { emoji: '⛳', name: 'スポーツ' },
    { emoji: '🎯', name: '目標地点' },
    // 水分補給・涼しいイメージのアイコン
    { emoji: '💧', name: '水' },
    { emoji: '🥤', name: '飲み物' },
    { emoji: '❄️', name: '涼しい' },
    { emoji: '⛄', name: '氷' },
    { emoji: '⛲', name: '噴水' },
    { emoji: '☂️', name: '日陰' },
    { emoji: '🌊', name: '水辺' },
    { emoji: '🌴', name: 'オアシス' }
  ];

  // データ取得関数
  const fetchBuildings = useCallback(async () => {
    try {
      console.log('Fetching buildings data...');
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);
      
      const response = await fetch(`${API_BASE_URL}/api/buildings`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (response.ok) {
        const data = await response.json();
        console.log('Buildings data received:', data);
        if (data.type === 'FeatureCollection' && data.features) {
          setBuildings(data.features);
        }
      } else {
        console.error('Failed to fetch buildings:', response.status);
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.warn('Buildings fetch timeout');
      } else {
        console.error('Error fetching buildings:', error);
      }
    }
  }, []);

  const fetchCustomNodes = useCallback(async () => {
    try {
      console.log('Fetching custom nodes data...');
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);
      
      const response = await fetch(`${API_BASE_URL}/api/custom-nodes`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (response.ok) {
        const data = await response.json();
        console.log('Custom nodes data received:', data);
        setCustomNodes(data);
      } else {
        console.error('Failed to fetch custom nodes:', response.status);
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.warn('Custom nodes fetch timeout');
      } else {
        console.error('Error fetching custom nodes:', error);
      }
    }
  }, []);

  // 初期化
  useEffect(() => {
    fetchBuildings();
    fetchCustomNodes();
    
    // 現在時刻を設定
    const now = new Date();
    setSelectedTime(`${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`);
  }, [fetchBuildings, fetchCustomNodes]);

  // マップアイコン強調機能
  const enhanceMapIcons = useCallback(() => {
    const mapElement = document.querySelector('.leaflet-container');
    if (mapElement && hideOSMIcons) {
      mapElement.classList.add('hide-osm-icons');
    }
  }, [hideOSMIcons]);

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
      console.log('Request data:', requestData);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 90000); // 1.5分に延長

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
        const data: RouteInfo = await response.json();
        console.log('Route data received:', data);
        setRoute(data.route_points);
        setRouteInfo(data);
      } else {
        const errorText = await response.text();
        console.error('Server error:', errorText);
        alert(`ルート計算に失敗しました (${response.status}): ${errorText}`);
      }
    } catch (error) {
      console.error('Route calculation error:', error);
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          alert('リクエストがタイムアウトしました。もう一度お試しください。');
        } else if (error.message.includes('fetch') || error.message.includes('Failed to fetch') || error.message.includes('Load failed')) {
          alert(`🌐 ネットワークエラー: サーバーに接続できません。\nAPI URL: ${API_BASE_URL}\n\nWiFi接続を確認してください。`);
        } else {
          alert(`エラーが発生しました: ${error.message}`);
        }
      } else {
        alert('不明なエラーが発生しました');
      }
    } finally {
      setLoading(false);
    }
  }, [startPoint, endPoint, transportMode, selectedTime, usesDijkstra]);

  // ルート比較（ダイクストラ）
  const compareRoutes = useCallback(async () => {
    if (!startPoint || !endPoint) {
      alert('開始地点と終了地点を設定してください');
      return;
    }

    setLoading(true);
    
    try {
      const now = new Date();
      const time = selectedTime || `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
      const date = now.toISOString().split('T')[0];

      const requestData = {
        start: [startPoint[1], startPoint[0]],
        end: [endPoint[1], endPoint[0]],
        time,
        date,
        transport_mode: transportMode
      };

      console.log('Comparing routes...');

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000); // 2分に延長

      const response = await fetch(`${API_BASE_URL}/api/route/compare`, {
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
        console.log('Route comparison received:', data);
        setComparison(data);
        
        // ダイクストラ法の結果がある場合はそれを表示
        if (data.dijkstra_route && data.dijkstra_route.route_points) {
          setRoute(data.dijkstra_route.route_points);
          setRouteInfo(data.dijkstra_route);
          alert('✅ ダイクストラ法で最適化されたルートが見つかりました！');
        } else if (data.simple_route && data.simple_route.route_points) {
          // フォールバックとしてシンプル法のルートを表示
          setRoute(data.simple_route.route_points);
          setRouteInfo(data.simple_route);
          alert('⚠️ ダイクストラ法では最適パスが見つからなかったため、通常ルートを表示します');
        } else {
          alert('❌ ルート計算に失敗しました');
        }
      } else {
        const errorText = await response.text();
        console.error('Server error:', errorText);
        
        // エラーメッセージを改善
        if (response.status === 408 || errorText.includes('timeout')) {
          alert('⏰ ダイクストラ計算がタイムアウトしました。通常のルート計算をお試しください。');
        } else if (errorText.includes('No path found')) {
          alert('🚫 ダイクストラ法で最適パスが見つかりません。通常のルート計算をお試しください。');
        } else {
          alert(`❌ ルート比較に失敗しました: ${errorText}`);
        }
      }
    } catch (error) {
      console.error('Route comparison error:', error);
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          alert('⏰ ダイクストラ計算がタイムアウトしました（2分）。距離が長すぎる可能性があります。');
        } else if (error.message.includes('Failed to fetch') || error.message.includes('Load failed')) {
          alert(`🌐 ネットワークエラー: サーバーに接続できません。\nAPI URL: ${API_BASE_URL}\n\nWiFi接続を確認してください。`);
        } else {
          alert(`❌ ダイクストラ計算エラー: ${error.message}`);
        }
      } else {
        alert('❌ 不明なエラーが発生しました');
      }
    } finally {
      setLoading(false);
    }
  }, [startPoint, endPoint, transportMode, selectedTime]);

  const clearRoute = useCallback(() => {
    setStartPoint(null);
    setEndPoint(null);
    setRoute([]);
    setRouteInfo(null);
    setComparison(null);
  }, []);

  // カスタムノード追加
  const addCustomNode = useCallback(async (lat: number, lng: number) => {
    triggerHaptic();
    
    const nodeName = prompt('ノード名を入力してください:', `カスタムポイント ${customNodes.length + 1}`);
    if (!nodeName) return;
    
    const nodeType = prompt('ノードタイプを入力してください:', 'custom') || 'custom';
    const description = prompt('説明を入力してください（任意）:', '');
    const createdBy = prompt('作成者名を入力してください（任意）:', 'anonymous') || 'anonymous';
    
    // アイコン選択
    const iconMessage = iconOptions
      .map((icon, index) => `${index + 1}. ${icon.emoji} ${icon.name}`)
      .join('\n');
    
    const iconChoice = prompt(`アイコンを選択してください (1-${iconOptions.length}):\n\n${iconMessage}`, '1');
    const iconIndex = Math.max(1, Math.min(iconOptions.length, parseInt(iconChoice || '1') || 1)) - 1;
    const selectedIcon = iconOptions[iconIndex];
    
    const nodeColor = prompt('ノードの色を入力してください（例: #ff4444）:', '#ff4444') || '#ff4444';
    
    try {
      const newNodeData = {
        name: nodeName,
        latitude: lat,
        longitude: lng,
        node_type: nodeType,
        description: description || undefined,
        created_by: createdBy,
        icon_type: selectedIcon.emoji,
        color: nodeColor
      };
      
      console.log('Creating custom node:', newNodeData);
      
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);
      
      const response = await fetch(`${API_BASE_URL}/api/custom-nodes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newNodeData),
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (response.ok) {
        const createdNode = await response.json();
        console.log('Custom node created:', createdNode);
        
        // ローカル状態を更新
        setCustomNodes(prev => [...prev, createdNode]);
        setCustomNodeMode(false);
        
        alert(`✅ ノード「${nodeName}」を追加しました！`);
      } else {
        const errorText = await response.text();
        console.error('Server error:', errorText);
        alert(`カスタムノードの作成に失敗しました: ${errorText}`);
      }
    } catch (error) {
      console.error('Custom node creation error:', error);
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          alert('リクエストがタイムアウトしました。もう一度お試しください。');
        } else {
          alert(`エラーが発生しました: ${error.message}`);
        }
      } else {
        alert('不明なエラーが発生しました');
      }
    }
  }, [customNodes.length, iconOptions]);

  // カスタムノード削除
  const removeCustomNode = useCallback(async (nodeId: number) => {
    if (!confirm('このノードを削除しますか？')) return;
    
    try {
      console.log('Deleting custom node:', nodeId);
      
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);
      
      const response = await fetch(`${API_BASE_URL}/api/custom-nodes/${nodeId}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (response.ok) {
        console.log('Custom node deleted');
        
        // ローカル状態を更新
        setCustomNodes(prev => prev.filter(node => node.id !== nodeId));
        
        alert('✅ ノードを削除しました');
      } else {
        const errorText = await response.text();
        console.error('Server error:', errorText);
        alert(`ノードの削除に失敗しました: ${errorText}`);
      }
    } catch (error) {
      console.error('Custom node deletion error:', error);
      alert('ノードの削除に失敗しました');
    }
  }, []);

  // ボトムシートコンテンツ
  const BottomSheetContent = () => {
    switch (activeTab) {
      case 'route':
        return (
          <div className="bottom-sheet-content">
            <h3>ルート検索</h3>
            <div style={{ fontSize: '11px', color: '#666', marginBottom: '8px', wordBreak: 'break-all' }}>
              🔗 {API_BASE_URL}
            </div>
            <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
              <select 
                value={transportMode} 
                onChange={(e) => setTransportMode(e.target.value)}
                style={{
                  padding: '12px',
                  borderRadius: '8px',
                  border: '1px solid #ddd',
                  minHeight: '48px',
                  flex: '1',
                  minWidth: '120px'
                }}
              >
                <option value="walk">🚶 徒歩</option>
                <option value="bike">🚲 自転車</option>
                <option value="car">🚗 車</option>
              </select>
              
              <button 
                onClick={calculateRoute} 
                disabled={!startPoint || !endPoint || loading}
                style={{
                  padding: '12px 24px',
                  backgroundColor: 'var(--primary-cool)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  minHeight: '48px',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  opacity: loading ? 0.6 : 1
                }}
              >
                {loading ? '計算中... (最大1.5分)' : 'ルート計算'}
              </button>
              
              <button 
                onClick={compareRoutes} 
                disabled={!startPoint || !endPoint || loading}
                style={{
                  padding: '12px 24px',
                  backgroundColor: '#667eea',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  minHeight: '48px',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  opacity: loading ? 0.6 : 1
                }}
              >
                {loading ? '比較中... (最大2分)' : 'ダイクストラ比較'}
              </button>
              
              <button 
                onClick={clearRoute}
                style={{
                  padding: '12px 24px',
                  backgroundColor: '#666',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  minHeight: '48px',
                  cursor: 'pointer'
                }}
              >
                クリア
              </button>
              
              <button 
                onClick={async () => {
                  try {
                    const response = await fetch(`${API_BASE_URL}/health`);
                    const data = await response.json();
                    alert(`✅ サーバー接続OK\nURL: ${API_BASE_URL}\nStatus: ${data.status}`);
                  } catch (error) {
                    alert(`❌ サーバー接続エラー\nURL: ${API_BASE_URL}\nError: ${error}`);
                  }
                }}
                style={{
                  padding: '8px 16px',
                  backgroundColor: '#28a745',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  minHeight: '36px',
                  fontSize: '12px',
                  cursor: 'pointer'
                }}
              >
                🔍 接続テスト
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
          </div>
        );

      case 'nodes':
        return (
          <div className="bottom-sheet-content">
            <h3>カスタムノード</h3>
            <div style={{ marginBottom: '16px' }}>
              <button
                onClick={() => setCustomNodeMode(!customNodeMode)}
                style={{
                  padding: '12px 24px',
                  backgroundColor: customNodeMode ? '#ef4444' : 'var(--primary-cool)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  width: '100%',
                  minHeight: '48px',
                  cursor: 'pointer'
                }}
              >
                {customNodeMode ? '📍 ノード追加モード終了' : '📍 ノード追加モード'}
              </button>
            </div>
            
            <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
              {customNodes.map((node) => (
                <div
                  key={node.id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '12px',
                    backgroundColor: 'white',
                    border: '1px solid #ddd',
                    borderRadius: '8px',
                    marginBottom: '8px'
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 'bold' }}>
                      {node.icon_type} {node.name}
                    </div>
                    <div style={{ fontSize: '12px', color: '#666' }}>
                      {node.node_type} | {node.created_by}
                    </div>
                    {node.description && (
                      <div style={{ fontSize: '12px', color: '#888', marginTop: '4px' }}>
                        {node.description}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => removeCustomNode(node.id)}
                    style={{
                      background: '#ef4444',
                      border: 'none',
                      color: 'white',
                      borderRadius: '4px',
                      padding: '6px 12px',
                      cursor: 'pointer',
                      fontSize: '12px'
                    }}
                  >
                    削除
                  </button>
                </div>
              ))}
            </div>
          </div>
        );

      case 'settings':
        return (
          <div className="bottom-sheet-content">
            <h3>設定</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '12px', minHeight: '48px' }}>
                <input
                  type="checkbox"
                  checked={usesDijkstra}
                  onChange={(e) => setUsesDijkstra(e.target.checked)}
                  style={{ width: '20px', height: '20px' }}
                />
                ダイクストラ法を使用
              </label>
              
              <label style={{ display: 'flex', alignItems: 'center', gap: '12px', minHeight: '48px' }}>
                <input
                  type="checkbox"
                  checked={autoUpdate}
                  onChange={(e) => setAutoUpdate(e.target.checked)}
                  style={{ width: '20px', height: '20px' }}
                />
                自動更新
              </label>
              
              <label style={{ display: 'flex', alignItems: 'center', gap: '12px', minHeight: '48px' }}>
                時刻設定:
                <input
                  type="time"
                  value={selectedTime}
                  onChange={(e) => setSelectedTime(e.target.value)}
                  style={{ padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                />
              </label>
            </div>
          </div>
        );

      default:
        return (
          <div className="bottom-sheet-content">
            <h3>地図情報</h3>
            <div style={{ fontSize: '14px', color: '#666' }}>
              {customNodeMode && <div style={{ color: 'var(--comfort-warm)' }}>📌 地図をタップしてノード追加</div>}
              {!customNodeMode && !startPoint && <div>📍 開始地点をタップしてください</div>}
              {!customNodeMode && startPoint && !endPoint && <div>🎯 終了地点をタップしてください</div>}
              {!customNodeMode && startPoint && endPoint && <div style={{ color: 'var(--comfort-comfortable)' }}>✅ ルート計算できます</div>}
            </div>
          </div>
        );
    }
  };

  // Bottom Navigation
  const BottomNavigation = () => {
    const navItems = [
      { id: 'route', icon: '🗺️', label: 'ルート' },
      { id: 'nodes', icon: '📍', label: 'ノード' },
      { id: 'settings', icon: '⚙️', label: '設定' }
    ];

    return (
      <nav className="bottom-nav">
        {navItems.map((item) => (
          <div
            key={item.id}
            className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
            onClick={() => {
              setActiveTab(item.id as 'route' | 'nodes' | 'settings');
              if (customNodeMode && item.id !== 'nodes') {
                setCustomNodeMode(false);
              }
            }}
          >
            <div className="nav-icon">{item.icon}</div>
            <div className="nav-label">{item.label}</div>
          </div>
        ))}
      </nav>
    );
  };

  return (
    <div className="app-container">
      {/* Map Area - 70-80% of screen */}
      <div className="map-area">
        <MapContainer
          center={[35.6917, 139.7036]} // 新宿駅
          zoom={14}
          style={{ height: '100%', width: '100%' }}
          className={hideOSMIcons ? 'hide-osm-icons' : ''}
        >
          {hideOSMIcons && (
            <div className="icon-control-test">
              OSMアイコン非表示モード
            </div>
          )}
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          />
          
          <MapClickHandler
            startPoint={startPoint}
            endPoint={endPoint}
            setStartPoint={setStartPoint}
            setEndPoint={setEndPoint}
            setRoute={setRoute}
            setRouteInfo={setRouteInfo}
            onMapUpdate={enhanceMapIcons}
            customNodeMode={customNodeMode}
            onAddCustomNode={addCustomNode}
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
          
          {/* カスタムノード表示 */}
          {customNodes.map((node) => (
            <Marker
              key={node.id}
              position={[node.latitude, node.longitude]}
              icon={createCustomNodeIcon(node.icon_type, node.color)}
            >
              <Popup>
                <div>
                  <strong>{node.name}</strong><br />
                  タイプ: {node.node_type}<br />
                  作成者: {node.created_by}<br />
                  {node.description && (
                    <>説明: {node.description}<br /></>
                  )}
                  <button
                    onClick={() => removeCustomNode(node.id)}
                    style={{
                      background: '#ef4444',
                      border: 'none',
                      color: 'white',
                      borderRadius: '4px',
                      padding: '4px 8px',
                      cursor: 'pointer',
                      fontSize: '12px',
                      marginTop: '8px'
                    }}
                  >
                    削除
                  </button>
                </div>
              </Popup>
            </Marker>
          ))}

          {route.length > 1 && (
            <Polyline
              positions={route.map(point => [point.latitude, point.longitude])}
              color="#2563eb"
              weight={4}
              opacity={0.8}
            />
          )}

          {/* 建物のポリゴン表示 */}
          {buildings.map((building, index) => {
            try {
              const coordinates = building.geometry.coordinates[0];
              const latLngs = coordinates.map(coord => [coord[1], coord[0]] as [number, number]);
              
              const height = building.properties.height || 10;
              const opacity = Math.min(0.6, Math.max(0.2, height / 50));
              const fillColor = height > 30 ? '#8b5cf6' : height > 15 ? '#3b82f6' : '#10b981';
              
              return (
                <Polygon
                  key={`building-${building.properties.osm_id}-${index}`}
                  positions={latLngs}
                  color="#374151"
                  weight={1}
                  opacity={0.8}
                  fillColor={fillColor}
                  fillOpacity={opacity}
                >
                  <Popup>
                    <div>
                      <strong>建物 ID: {building.properties.osm_id}</strong><br/>
                      タイプ: {building.properties.building}<br/>
                      推定高さ: {Math.round(height)}m
                    </div>
                  </Popup>
                </Polygon>
              );
            } catch (error) {
              console.warn('Building polygon error:', error, building);
              return null;
            }
          })}

        </MapContainer>

        {/* Map Controls */}
        <div className="map-controls">
          <button
            className="map-control-btn"
            onClick={() => setHideOSMIcons(!hideOSMIcons)}
            title={hideOSMIcons ? 'OSMアイコンを表示' : 'OSMアイコンを非表示'}
          >
            {hideOSMIcons ? '👁️' : '🙈'}
          </button>
        </div>
      </div>

      {/* Bottom Sheet */}
      <div className={`bottom-sheet ${bottomSheetState}`}>
        <div 
          className="bottom-sheet-handle"
          onClick={() => {
            setBottomSheetState(prev => 
              prev === 'expanded' ? 'peek' : 
              prev === 'peek' ? 'expanded' : 'peek'
            );
          }}
        />
        
        <BottomSheetContent />
      </div>

      {/* Bottom Navigation */}
      <BottomNavigation />
    </div>
  );
}

export default App;