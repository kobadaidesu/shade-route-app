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
  const [showBuildings, setShowBuildings] = useState(true);
  const [customNodes, setCustomNodes] = useState<CustomNode[]>([]);
  const [customNodeMode, setCustomNodeMode] = useState(false);

  // UI状態
  const [bottomSheetState, setBottomSheetState] = useState<'collapsed' | 'peek' | 'expanded'>('peek');
  const [activeTab, setActiveTab] = useState<'route' | 'nodes' | 'settings'>('route');
  const [isBottomSheetVisible, setIsBottomSheetVisible] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartY, setDragStartY] = useState(0);
  const [dragCurrentY, setDragCurrentY] = useState(0);

  // ルート計算
  const calculateRoute = useCallback(async (forceDijkstra = false) => {
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
      
      const shouldUseDijkstra = forceDijkstra || usesDijkstra;
      const endpoint = shouldUseDijkstra ? '/api/route/dijkstra' : '/api/route/shade-avoid';
      console.log('Sending request to:', `${API_BASE_URL}${endpoint}`, 'Force Dijkstra:', forceDijkstra);

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
        setUsesDijkstra(shouldUseDijkstra);
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

  const fetchCustomNodes = useCallback(() => {
    try {
      console.log('Loading custom nodes from localStorage...');
      const stored = localStorage.getItem('customNodes');
      if (stored) {
        const nodes = JSON.parse(stored);
        console.log('Custom nodes loaded:', nodes);
        setCustomNodes(nodes);
      } else {
        console.log('No custom nodes found in localStorage');
        setCustomNodes([]);
      }
    } catch (error) {
      console.error('Error loading custom nodes from localStorage:', error);
      setCustomNodes([]);
    }
  }, []);

  const saveCustomNodes = useCallback((nodes: CustomNode[]) => {
    try {
      localStorage.setItem('customNodes', JSON.stringify(nodes));
      console.log('Custom nodes saved to localStorage:', nodes);
    } catch (error) {
      console.error('Error saving custom nodes to localStorage:', error);
    }
  }, []);

  // ノード追加用の状態
  const [showNodeDialog, setShowNodeDialog] = useState(false);
  const [pendingNodeLocation, setPendingNodeLocation] = useState<[number, number] | null>(null);
  const [selectedIcon, setSelectedIcon] = useState('📍');
  const [nodeName, setNodeName] = useState('');
  const [nodeDescription, setNodeDescription] = useState('');
  const [selectedNodeType, setSelectedNodeType] = useState('landmark');

  // ノードタイプオプション
  const nodeTypeOptions = [
    { value: 'landmark', label: '🗺️ ランドマーク' },
    { value: 'shop', label: '🏪 店舗' },
    { value: 'station', label: '🚉 駅・停留所' },
    { value: 'food', label: '🍽️ 飲食店' },
    { value: 'facility', label: '🏢 施設' },
    { value: 'nature', label: '🌳 自然' },
    { value: 'other', label: '📍 その他' }
  ];

  // カスタムノード追加関数
  const onAddCustomNode = useCallback((lat: number, lng: number) => {
    setPendingNodeLocation([lat, lng]);
    setShowNodeDialog(true);
    setNodeName('');
    setNodeDescription('');
    setSelectedIcon('📍');
    setSelectedNodeType('landmark');
  }, []);

  // ノード作成を実行
  const createCustomNode = useCallback(() => {
    if (!pendingNodeLocation || !nodeName.trim()) {
      alert('ノード名を入力してください');
      return;
    }

    try {
      const newNode: CustomNode = {
        id: Date.now(), // 簡単なID生成
        name: nodeName.trim(),
        latitude: pendingNodeLocation[0],
        longitude: pendingNodeLocation[1],
        node_type: selectedNodeType,
        description: nodeDescription.trim() || '',
        icon_type: selectedIcon,
        color: '#ff4444',
        created_by: 'user',
        created_at: new Date().toISOString()
      };

      console.log('Creating custom node:', newNode);

      // 既存のノードリストに追加
      const updatedNodes = [...customNodes, newNode];
      setCustomNodes(updatedNodes);
      saveCustomNodes(updatedNodes);
      
      // ダイアログを閉じてモードを終了
      setShowNodeDialog(false);
      setPendingNodeLocation(null);
      setCustomNodeMode(false);
      
      alert('ノードを追加しました！');
    } catch (error) {
      console.error('Error creating custom node:', error);
      alert('ノードの追加中にエラーが発生しました');
    }
  }, [pendingNodeLocation, nodeName, nodeDescription, selectedIcon, selectedNodeType, customNodes, saveCustomNodes]);

  // ノード追加ダイアログをキャンセル
  const cancelNodeDialog = useCallback(() => {
    setShowNodeDialog(false);
    setPendingNodeLocation(null);
  }, []);

  // スライド操作のハンドラー
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    e.stopPropagation(); // イベントバブリングを防ぐ
    setIsDragging(true);
    setDragStartY(e.touches[0].clientY);
    setDragCurrentY(e.touches[0].clientY);
  }, []);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (!isDragging) return;
    e.preventDefault(); // デフォルトのスクロール動作を防ぐ
    e.stopPropagation(); // イベントバブリングを防ぐ
    setDragCurrentY(e.touches[0].clientY);
  }, [isDragging]);

  const handleTouchEnd = useCallback((e: React.TouchEvent) => {
    if (!isDragging) return;
    e.stopPropagation(); // イベントバブリングを防ぐ
    setIsDragging(false);
    
    const deltaY = dragCurrentY - dragStartY;
    const threshold = 50; // 50px以上のドラッグで状態変更
    
    if (deltaY > threshold) {
      // 下にドラッグ - 縮小
      if (bottomSheetState === 'expanded') {
        setBottomSheetState('peek');
      } else if (bottomSheetState === 'peek') {
        setBottomSheetState('collapsed');
      }
    } else if (deltaY < -threshold) {
      // 上にドラッグ - 拡大
      if (bottomSheetState === 'collapsed') {
        setBottomSheetState('peek');
      } else if (bottomSheetState === 'peek') {
        setBottomSheetState('expanded');
      }
    }
  }, [isDragging, dragCurrentY, dragStartY, bottomSheetState]);

  const handleMouseStart = useCallback((e: React.MouseEvent) => {
    setIsDragging(true);
    setDragStartY(e.clientY);
    setDragCurrentY(e.clientY);
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDragging) return;
    setDragCurrentY(e.clientY);
  }, [isDragging]);

  const handleMouseEnd = useCallback(() => {
    if (!isDragging) return;
    setIsDragging(false);
    
    const deltaY = dragCurrentY - dragStartY;
    const threshold = 50;
    
    if (deltaY > threshold) {
      if (bottomSheetState === 'expanded') {
        setBottomSheetState('peek');
      } else if (bottomSheetState === 'peek') {
        setBottomSheetState('collapsed');
      }
    } else if (deltaY < -threshold) {
      if (bottomSheetState === 'collapsed') {
        setBottomSheetState('peek');
      } else if (bottomSheetState === 'peek') {
        setBottomSheetState('expanded');
      }
    }
  }, [isDragging, dragCurrentY, dragStartY, bottomSheetState]);

  // 初期化
  useEffect(() => {
    fetchBuildings();
    fetchCustomNodes();
    
    // 現在時刻を設定
    const now = new Date();
    setSelectedTime(`${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`);

    // マウスイベントのグローバルハンドラー
    const handleGlobalMouseMove = (e: MouseEvent) => {
      if (isDragging) {
        setDragCurrentY(e.clientY);
      }
    };

    const handleGlobalMouseUp = () => {
      if (isDragging) {
        handleMouseEnd();
      }
    };

    document.addEventListener('mousemove', handleGlobalMouseMove);
    document.addEventListener('mouseup', handleGlobalMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleGlobalMouseMove);
      document.removeEventListener('mouseup', handleGlobalMouseUp);
    };
  }, [fetchBuildings, fetchCustomNodes, isDragging, handleMouseEnd]);

  // ルートポイントをLeafletのLatLng形式に変換
  const routeLatLngs = route.map(point => [point.latitude, point.longitude] as [number, number]);

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
    { emoji: '💧', name: '水' },
    { emoji: '🥤', name: '飲み物' },
    { emoji: '❄️', name: '涼しい' },
    { emoji: '⛄', name: '氷' },
    { emoji: '⛲', name: '噴水' },
    { emoji: '☂️', name: '日陰' },
    { emoji: '🌊', name: '水辺' },
    { emoji: '🌴', name: 'オアシス' }
  ];

  // タブコンテンツをレンダリング
  const renderTabContent = () => {
    switch (activeTab) {
      case 'route':
        return (
          <div style={{ padding: '24px' }}>
            <h2 style={{
              fontSize: '24px',
              fontWeight: '700',
              color: '#1a202c',
              marginBottom: '24px',
              fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
            }}>
              日陰ルート
            </h2>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '12px' }}>
                <button
                  onClick={() => calculateRoute(true)}
                  disabled={!startPoint || !endPoint || loading}
                  style={{
                    padding: '16px 20px',
                    backgroundColor: (!startPoint || !endPoint || loading) ? '#e2e8f0' : '#3182ce',
                    color: (!startPoint || !endPoint || loading) ? '#a0aec0' : 'white',
                    border: 'none',
                    borderRadius: '12px',
                    fontSize: '16px',
                    fontWeight: '600',
                    cursor: (!startPoint || !endPoint || loading) ? 'not-allowed' : 'pointer',
                    transition: 'all 0.2s ease',
                    boxShadow: (!startPoint || !endPoint || loading) ? 'none' : '0 4px 12px rgba(49, 130, 206, 0.15)',
                    transform: (!startPoint || !endPoint || loading) ? 'none' : 'translateY(0)',
                    fontFamily: 'inherit'
                  }}
                  onMouseEnter={(e) => {
                    if (!(!startPoint || !endPoint || loading)) {
                      e.currentTarget.style.transform = 'translateY(-1px)';
                      e.currentTarget.style.boxShadow = '0 6px 16px rgba(49, 130, 206, 0.2)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!(!startPoint || !endPoint || loading)) {
                      e.currentTarget.style.transform = 'translateY(0)';
                      e.currentTarget.style.boxShadow = '0 4px 12px rgba(49, 130, 206, 0.15)';
                    }
                  }}
                >
                  {loading ? '計算中...' : '日陰ルート検索'}
                </button>
                
                <button
                  onClick={() => {
                    setStartPoint(null);
                    setEndPoint(null);
                    setRoute([]);
                    setRouteInfo(null);
                  }}
                  style={{
                    padding: '16px 20px',
                    backgroundColor: 'transparent',
                    color: '#718096',
                    border: '2px solid #e2e8f0',
                    borderRadius: '12px',
                    fontSize: '16px',
                    fontWeight: '600',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    fontFamily: 'inherit'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = '#cbd5e0';
                    e.currentTarget.style.backgroundColor = '#f7fafc';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = '#e2e8f0';
                    e.currentTarget.style.backgroundColor = 'transparent';
                  }}
                >
                  クリア
                </button>
              </div>

              {routeInfo && (
                <div style={{
                  backgroundColor: 'white',
                  borderRadius: '16px',
                  boxShadow: '0 4px 20px rgba(0, 0, 0, 0.08)',
                  padding: '24px',
                  border: '1px solid #f1f5f9'
                }}>
                  <h3 style={{
                    fontSize: '18px',
                    fontWeight: '600',
                    color: '#2d3748',
                    marginBottom: '20px',
                    fontFamily: 'inherit'
                  }}>
                    ルート情報
                  </h3>
                  <div style={{ 
                    display: 'grid', 
                    gridTemplateColumns: 'repeat(3, 1fr)', 
                    gap: '20px',
                    marginBottom: '16px'
                  }}>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '12px', color: '#718096', fontWeight: '500', marginBottom: '4px' }}>距離</div>
                      <div style={{ fontSize: '24px', fontWeight: '700', color: '#38a169' }}>
                        {Math.round(routeInfo.total_distance)}m
                      </div>
                    </div>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '12px', color: '#718096', fontWeight: '500', marginBottom: '4px' }}>時間</div>
                      <div style={{ fontSize: '24px', fontWeight: '700', color: '#ed8936' }}>
                        {routeInfo.estimated_time}分
                      </div>
                    </div>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '12px', color: '#718096', fontWeight: '500', marginBottom: '4px' }}>日陰率</div>
                      <div style={{ fontSize: '24px', fontWeight: '700', color: '#319795' }}>
                        {Math.round(routeInfo.average_shade_ratio * 100)}%
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <div style={{
                padding: '16px 20px',
                borderRadius: '12px',
                backgroundColor: !startPoint ? '#fffbeb' : 
                               (startPoint && !endPoint) ? '#f0fff4' : '#eff6ff',
                border: `2px solid ${!startPoint ? '#fed7aa' : 
                                     (startPoint && !endPoint) ? '#9ae6b4' : '#bfdbfe'}`,
                color: !startPoint ? '#c05621' : 
                       (startPoint && !endPoint) ? '#276749' : '#1e40af',
                fontWeight: '500',
                fontSize: '14px'
              }}>
                {!startPoint && '開始地点をタップしてください'}
                {startPoint && !endPoint && '終了地点をタップしてください'}
                {startPoint && endPoint && '両地点設定完了 - ルート検索できます'}
              </div>
            </div>
          </div>
        );

      case 'nodes':
        return (
          <div className="bottom-sheet-content">
            <h3 style={{
              margin: '0 0 20px 0',
              fontSize: '20px',
              fontWeight: '600',
              color: '#1a1a1a',
              letterSpacing: '-0.3px',
              fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif'
            }}>カスタムノード</h3>
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
                    background: '#f8f9fa',
                    padding: '12px',
                    borderRadius: '8px',
                    marginBottom: '8px',
                    border: '1px solid #e9ecef'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '20px' }}>{node.icon_type}</span>
                    <div>
                      <strong>{node.name}</strong>
                      <div style={{ fontSize: '12px', color: '#666' }}>
                        {node.node_type} | {node.created_by}
                      </div>
                    </div>
                  </div>
                  {node.description && (
                    <div style={{ fontSize: '14px', marginTop: '4px' }}>
                      {node.description}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        );

      case 'settings':
        return (
          <div className="bottom-sheet-content">
            <h3 style={{
              margin: '0 0 20px 0',
              fontSize: '20px',
              fontWeight: '600',
              color: '#1a1a1a',
              letterSpacing: '-0.3px',
              fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif'
            }}>設定</h3>
            
            <div style={{ marginBottom: '24px' }}>
              <h4>移動手段</h4>
              <div style={{ display: 'flex', gap: '8px' }}>
                {['walk', 'bike', 'car'].map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setTransportMode(mode)}
                    style={{
                      flex: 1,
                      padding: '8px 16px',
                      backgroundColor: transportMode === mode ? 'var(--primary-cool)' : '#f8f9fa',
                      color: transportMode === mode ? 'white' : '#333',
                      border: '1px solid #ddd',
                      borderRadius: '6px',
                      cursor: 'pointer'
                    }}
                  >
                    {mode === 'walk' ? '🚶 徒歩' : mode === 'bike' ? '🚲 自転車' : '🚗 車'}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ marginBottom: '24px' }}>
              <h4>計算時刻</h4>
              <input
                type="time"
                value={selectedTime}
                onChange={(e) => setSelectedTime(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px',
                  border: '1px solid #ddd',
                  borderRadius: '6px'
                }}
              />
            </div>

            <div style={{ marginBottom: '24px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input
                  type="checkbox"
                  checked={showBuildings}
                  onChange={(e) => {
                    console.log('建物表示切り替え:', e.target.checked);
                    setShowBuildings(e.target.checked);
                  }}
                />
                建物を表示 (現在: {showBuildings ? 'ON' : 'OFF'})
              </label>
              
              {/* テスト用ボタン */}
              <div style={{ marginTop: '8px' }}>
                <button 
                  onClick={() => setShowBuildings(!showBuildings)}
                  style={{
                    padding: '8px 16px',
                    backgroundColor: showBuildings ? '#ff4444' : '#44ff44',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer'
                  }}
                >
                  {showBuildings ? '建物を隠す' : '建物を表示'}
                </button>
              </div>
            </div>

            <div style={{ marginBottom: '24px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input
                  type="checkbox"
                  checked={hideOSMIcons}
                  onChange={(e) => setHideOSMIcons(e.target.checked)}
                />
                OSMアイコンを非表示
              </label>
            </div>

            <div style={{ fontSize: '14px', color: '#666' }}>
              <div>建物データ: {buildings.length}件</div>
              <div>建物表示状態: {showBuildings ? '表示中' : '非表示'}</div>
              <div>描画される建物数: {showBuildings ? buildings.length : 0}件</div>
              <div>カスタムノード: {customNodes.length}件</div>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div 
      className="app-container"
      style={{
        height: window.innerWidth <= 430 ? '100dvh' : '100vh', // モバイルは100dvh
        width: '100vw',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        position: 'fixed',
        top: 0,
        left: 0,
        margin: 0,
        padding: 0,
        background: '#000' // 黒い背景を確実に隠す
      }}
    >
      {/* Map Area */}
      <div 
        className="map-area"
        style={{
          flex: 1,
          position: 'relative',
          width: '100%',
          height: window.innerWidth <= 430 ? // モバイル判定
            'calc(100dvh - 56px)' : // モバイルは常にナビ分確保
            'calc(100vh - 56px)', // PC
          marginBottom: '0',
          background: '#f0f0f0' // 地図の背景色を設定
        }}
      >
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

          {/* Buildings */}
          {(() => {
            console.log('建物描画チェック - showBuildings:', showBuildings, 'buildings数:', buildings.length);
            return showBuildings && buildings.map((building, index) => {
            if (building.geometry && building.geometry.type === 'Polygon') {
              const coordinates = building.geometry.coordinates[0].map(coord => [coord[1], coord[0]] as [number, number]);
              return (
                <Polygon
                  key={`building-${index}`}
                  positions={coordinates}
                  fillColor="#4a90e2"
                  fillOpacity={0.3}
                  color="#2c5aa0"
                  weight={1}
                >
                  <Popup>
                    <div>
                      <strong>建物</strong><br/>
                      高さ: {building.properties.height || 'N/A'}m<br/>
                      タイプ: {building.properties.building || 'N/A'}
                    </div>
                  </Popup>
                </Polygon>
              );
            }
            return null;
          });
          })()}

          {/* Custom Nodes */}
          {customNodes.map((node) => {
            const customIcon = L.divIcon({
              className: 'custom-node-icon',
              html: `
                <div style="
                  background: ${node.color || '#ff4444'};
                  border: 2px solid white;
                  border-radius: 50%;
                  width: 32px;
                  height: 32px;
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  font-size: 16px;
                  box-shadow: 0 2px 6px rgba(0,0,0,0.3);
                ">${node.icon_type}</div>
              `,
              iconSize: [32, 32],
              iconAnchor: [16, 16]
            });

            return (
              <Marker
                key={`custom-node-${node.id}`}
                position={[node.latitude, node.longitude]}
                icon={customIcon}
              >
                <Popup>
                  <div>
                    <strong>{node.name}</strong><br/>
                    {node.description && <span>{node.description}<br/></span>}
                    タイプ: {node.node_type}<br/>
                    作成者: {node.created_by}
                  </div>
                </Popup>
              </Marker>
            );
          })}

          {routeLatLngs.length > 0 && (
            <Polyline 
              positions={routeLatLngs} 
              color={usesDijkstra ? "#ff9500" : "#ef4444"} 
              weight={4} 
              opacity={0.8}
            />
          )}

          {/* ルートポイントの日陰率を表示（ダイクストラ時のみ） */}
          {usesDijkstra && route.length > 0 && route.map((point, index) => {
            if (index % 3 === 0) { // 3ポイントごとに表示
              const shadePercentage = Math.round(point.shade_ratio * 100);
              return (
                <Marker
                  key={`shade-${index}`}
                  position={[point.latitude, point.longitude]}
                  icon={L.divIcon({
                    html: `<div style="background: rgba(0,0,0,0.7); color: white; padding: 2px 4px; border-radius: 3px; font-size: 10px;">${shadePercentage}%</div>`,
                    className: 'shade-marker',
                    iconSize: [30, 15],
                    iconAnchor: [15, 7]
                  })}
                />
              );
            }
            return null;
          })}
        </MapContainer>

        {/* Map Controls */}
        <div className="map-controls">
          <button className="map-control-btn">
            👁️
          </button>
        </div>
      </div>

      {/* Bottom Sheet */}
      {isBottomSheetVisible && (
        <div 
          className={`bottom-sheet ${bottomSheetState}`}
          style={{
            position: 'fixed',
            left: 0,
            right: 0,
            bottom: '56px',
            width: '100%',
            zIndex: 999,
            background: 'white',
            borderRadius: '20px 20px 0 0',
            boxShadow: '0 -4px 20px rgba(26, 26, 46, 0.5)',
            transition: isDragging ? 'none' : 'transform 0.3s ease',
            transform: (() => {
              if (isDragging) {
                const deltaY = dragCurrentY - dragStartY;
                const baseTransform = bottomSheetState === 'collapsed' ? 'calc(100% - 80px)' :
                                    bottomSheetState === 'peek' ? 'calc(100% - 200px)' :
                                    '0';
                return `translateY(${baseTransform}) translateY(${deltaY}px)`;
              }
              return bottomSheetState === 'collapsed' ? 'translateY(calc(100% - 80px))' :
                     bottomSheetState === 'peek' ? 'translateY(calc(100% - 200px))' :
                     'translateY(0)';
            })(),
            maxHeight: 'calc(100vh - 120px)'
          }}
        >
          <div 
            className="bottom-sheet-handle"
            style={{
              width: '100%',
              height: '40px', // タッチエリアを拡大
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: isDragging ? 'grabbing' : 'grab',
              margin: '0 0 16px 0',
              padding: '12px 0'
            }}
            onTouchStart={handleTouchStart}
            onTouchMove={handleTouchMove}
            onTouchEnd={handleTouchEnd}
            onMouseDown={handleMouseStart}
            onClick={() => {
              if (bottomSheetState === 'collapsed') {
                setBottomSheetState('peek');
              } else if (bottomSheetState === 'peek') {
                setBottomSheetState('expanded');
              } else {
                setBottomSheetState('collapsed');
              }
            }}
          >
            <div style={{
              width: '36px',
              height: '4px',
              background: '#ddd',
              borderRadius: '2px'
            }} />
          </div>
          <div 
            className="bottom-sheet-content"
            style={{
              padding: '0 20px 20px',
              maxHeight: bottomSheetState === 'expanded' ? '60vh' : '30vh',
              overflowY: 'auto'
            }}
          >
            {/* デバッグ情報 */}
            <div style={{
              backgroundColor: 'white',
              border: '1px solid #e2e8f0',
              borderRadius: '12px',
              padding: '16px',
              marginBottom: '16px',
              boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1)'
            }}>
              <div style={{
                fontSize: '14px',
                fontWeight: '600',
                color: '#4a5568',
                marginBottom: '12px'
              }}>
                Debug Info
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '12px', color: '#718096' }}>状態:</span>
                  <span style={{
                    backgroundColor: '#ebf8ff',
                    color: '#3182ce',
                    padding: '2px 8px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    fontWeight: '500'
                  }}>
                    {bottomSheetState}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '12px', color: '#718096' }}>ドラッグ:</span>
                  <span style={{
                    backgroundColor: isDragging ? '#f0fff4' : '#f7fafc',
                    color: isDragging ? '#38a169' : '#718096',
                    padding: '2px 8px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    fontWeight: '500'
                  }}>
                    {isDragging ? "Active" : "Inactive"}
                  </span>
                </div>
                {isDragging && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '12px', color: '#718096' }}>移動量:</span>
                    <span style={{
                      fontSize: '12px',
                      color: '#ed8936',
                      fontFamily: 'Monaco, "Cascadia Code", monospace'
                    }}>
                      {dragCurrentY - dragStartY}px
                    </span>
                  </div>
                )}
              </div>
            </div>
            {renderTabContent()}
          </div>
        </div>
      )}

      {/* Bottom Navigation */}
      <div style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        backgroundColor: isBottomSheetVisible ? 'white' : 'rgba(255, 255, 255, 0.95)',
        borderTop: isBottomSheetVisible ? '1px solid #e2e8f0' : 'none',
        backdropFilter: isBottomSheetVisible ? 'none' : 'blur(12px)',
        boxShadow: isBottomSheetVisible ? '0 -2px 8px rgba(0,0,0,0.1)' : '0 -1px 4px rgba(0,0,0,0.2)',
        height: '64px',
        zIndex: 1000,
        display: 'flex'
      }}>
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          color: activeTab === 'route' ? '#3182ce' : '#718096',
          transition: 'all 0.2s ease',
          borderRadius: '8px',
          margin: '4px'
        }}
        onClick={() => {
          if (activeTab === 'route' && isBottomSheetVisible) {
            setIsBottomSheetVisible(false);
          } else {
            setActiveTab('route');
            setIsBottomSheetVisible(true);
            setBottomSheetState('peek');
          }
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = '#ebf8ff';
          e.currentTarget.style.color = '#3182ce';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'transparent';
          e.currentTarget.style.color = activeTab === 'route' ? '#3182ce' : '#718096';
        }}
        >
          <div style={{ fontSize: '20px', marginBottom: '2px' }}>🗺️</div>
          <div style={{ fontSize: '12px', fontWeight: '600' }}>ルート</div>
        </div>
        
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          color: activeTab === 'nodes' ? '#3182ce' : '#718096',
          transition: 'all 0.2s ease',
          borderRadius: '8px',
          margin: '4px'
        }}
        onClick={() => {
          if (activeTab === 'nodes' && isBottomSheetVisible) {
            setIsBottomSheetVisible(false);
          } else {
            setActiveTab('nodes');
            setIsBottomSheetVisible(true);
            setBottomSheetState('peek');
          }
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = '#ebf8ff';
          e.currentTarget.style.color = '#3182ce';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'transparent';
          e.currentTarget.style.color = activeTab === 'nodes' ? '#3182ce' : '#718096';
        }}
        >
          <div style={{ fontSize: '20px', marginBottom: '2px' }}>📍</div>
          <div style={{ fontSize: '12px', fontWeight: '600' }}>ノード</div>
        </div>
        
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          color: activeTab === 'settings' ? '#3182ce' : '#718096',
          transition: 'all 0.2s ease',
          borderRadius: '8px',
          margin: '4px'
        }}
        onClick={() => {
          if (activeTab === 'settings' && isBottomSheetVisible) {
            setIsBottomSheetVisible(false);
          } else {
            setActiveTab('settings');
            setIsBottomSheetVisible(true);
            setBottomSheetState('peek');
          }
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = '#ebf8ff';
          e.currentTarget.style.color = '#3182ce';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'transparent';
          e.currentTarget.style.color = activeTab === 'settings' ? '#3182ce' : '#718096';
        }}
        >
          <div style={{ fontSize: '20px', marginBottom: '2px' }}>⚙️</div>
          <div style={{ fontSize: '12px', fontWeight: '600' }}>設定</div>
        </div>
      </div>

      {/* ノード追加ダイアログ */}
      {showNodeDialog && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 2000
        }}>
          <div style={{
            backgroundColor: 'white',
            padding: '24px',
            borderRadius: '12px',
            maxWidth: '90vw',
            maxHeight: '80vh',
            overflowY: 'auto',
            width: '400px'
          }}>
            <h3>📍 新しいノードを追加</h3>
            
            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
                ノード名 *
              </label>
              <input
                type="text"
                value={nodeName}
                onChange={(e) => setNodeName(e.target.value)}
                placeholder="例: 新宿駅、スタバ、公園など"
                style={{
                  width: '100%',
                  padding: '8px',
                  border: '1px solid #ddd',
                  borderRadius: '6px'
                }}
              />
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
                ノードタイプ
              </label>
              <select
                value={selectedNodeType}
                onChange={(e) => setSelectedNodeType(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px',
                  border: '1px solid #ddd',
                  borderRadius: '6px'
                }}
              >
                {nodeTypeOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
                アイコンを選択
              </label>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(6, 1fr)',
                gap: '8px',
                marginBottom: '8px'
              }}>
                {iconOptions.map((icon) => (
                  <button
                    key={icon.emoji}
                    onClick={() => setSelectedIcon(icon.emoji)}
                    style={{
                      padding: '8px',
                      border: selectedIcon === icon.emoji ? '2px solid var(--primary-cool)' : '1px solid #ddd',
                      borderRadius: '6px',
                      backgroundColor: selectedIcon === icon.emoji ? '#e3f2fd' : 'white',
                      cursor: 'pointer',
                      fontSize: '20px'
                    }}
                    title={icon.name}
                  >
                    {icon.emoji}
                  </button>
                ))}
              </div>
              <div style={{ fontSize: '12px', color: '#666' }}>
                選択中: {selectedIcon} ({iconOptions.find(i => i.emoji === selectedIcon)?.name})
              </div>
            </div>

            <div style={{ marginBottom: '24px' }}>
              <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
                説明（任意）
              </label>
              <textarea
                value={nodeDescription}
                onChange={(e) => setNodeDescription(e.target.value)}
                placeholder="このノードについての説明を入力..."
                rows={3}
                style={{
                  width: '100%',
                  padding: '8px',
                  border: '1px solid #ddd',
                  borderRadius: '6px',
                  resize: 'vertical'
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={createCustomNode}
                style={{
                  flex: 1,
                  padding: '12px',
                  backgroundColor: 'var(--primary-cool)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  fontWeight: 'bold'
                }}
              >
                ✅ ノードを追加
              </button>
              <button
                onClick={cancelNodeDialog}
                style={{
                  flex: 1,
                  padding: '12px',
                  backgroundColor: '#6c757d',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  cursor: 'pointer'
                }}
              >
                ❌ キャンセル
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;