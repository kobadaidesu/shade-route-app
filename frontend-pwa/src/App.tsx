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
  html: '<div style="background-color: #10b981; width: 20px; height: 20px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>',
  className: 'custom-marker',
  iconSize: [20, 20],
  iconAnchor: [10, 10]
});

const endIcon = L.divIcon({
  html: '<div style="background-color: #ef4444; width: 20px; height: 20px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>',
  className: 'custom-marker',
  iconSize: [20, 20],
  iconAnchor: [10, 10]
});

const customNodeIcon = L.divIcon({
  html: '<div style="background-color: #8b5cf6; width: 16px; height: 16px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>',
  className: 'custom-marker',
  iconSize: [16, 16],
  iconAnchor: [8, 8]
});

// デフォルトアイコン制御用アイコン（削除済み）

interface RoutePoint {
  longitude: number;
  latitude: number;
  shade_ratio: number;
}

interface RouteResponse {
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
  id: string;
  lat: number;
  lng: number;
  name: string;
  type: string;
  description?: string;
}


const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8005';

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
  setRouteInfo: (info: RouteResponse | null) => void;
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
    } else if (!endPoint) {
      setEndPoint([lat, lng]);
    } else {
      setStartPoint([lat, lng]);
      setEndPoint(null);
      setRoute([]);
      setRouteInfo(null);
    }
  }, [startPoint, endPoint, setStartPoint, setEndPoint, setRoute, setRouteInfo, customNodeMode, onAddCustomNode]);

  useMapEvents({
    click: handleMapClick,
    zoomend: onMapUpdate,
    moveend: onMapUpdate
  });
  return null;
});

function App() {
  const [startPoint, setStartPoint] = useState<[number, number] | null>(null);
  const [endPoint, setEndPoint] = useState<[number, number] | null>(null);
  const [route, setRoute] = useState<RoutePoint[]>([]);
  const [routeInfo, setRouteInfo] = useState<RouteResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [transportMode, setTransportMode] = useState('walk');
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [showBuildings, setShowBuildings] = useState(true);
  const [usesDijkstra, setUsesDijkstra] = useState(false);
  const [comparison, setComparison] = useState<any>(null);
  const [selectedTime, setSelectedTime] = useState('');
  const [autoUpdate, setAutoUpdate] = useState(false);
  const [hideOSMIcons, setHideOSMIcons] = useState(false);
  const [customNodes, setCustomNodes] = useState<CustomNode[]>(() => {
    try {
      const saved = localStorage.getItem('shade-route-custom-nodes');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [customNodeMode, setCustomNodeMode] = useState(false);
  const [showCustomNodes, setShowCustomNodes] = useState(true);
  // const [shadeTimeline, setShadeTimeline] = useState<any>(null);
  // const [currentShadeInfo, setCurrentShadeInfo] = useState<any>(null);


  // 建物データを取得（メモ化）
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

  // シンプルなアイコン強調機能
  const enhanceMapIcons = useCallback(() => {
    // CSSクラスによる制御のみ
    console.log('Map icons enhancement applied via CSS');
  }, []);

  // コンポーネントマウント時にデータを取得
  useEffect(() => {
    fetchBuildings();
    
    // 現在時刻を設定
    const now = new Date();
    setSelectedTime(`${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`);
  }, [fetchBuildings]);

  // 自動更新機能
  useEffect(() => {
    if (!autoUpdate || !route.length) return;

    const interval = setInterval(() => {
      const now = new Date();
      const newTime = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
      setSelectedTime(newTime);
      
      // ルートがある場合は自動再計算
      if (startPoint && endPoint) {
        // calculateRoute(); // 循環参照を避けるため、一時的にコメントアウト
      }
    }, 300000); // 5分ごと

    return () => clearInterval(interval);
  }, [autoUpdate, route.length, startPoint, endPoint]);

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
      const timeoutId = setTimeout(() => controller.abort(), 45000); // ダイクストラ法は時間がかかるため

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestData),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      console.log('Response status:', response.status);
      
      if (response.ok) {
        const data: RouteResponse = await response.json();
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
        } else if (error.message.includes('fetch')) {
          alert('サーバーに接続できません。サーバーが起動しているか確認してください。');
        } else {
          alert(`エラーが発生しました: ${error.message}`);
        }
      } else {
        alert('不明なエラーが発生しました');
      }
    } finally {
      setLoading(false);
    }
  }, [startPoint, endPoint, transportMode, usesDijkstra]);

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
      const timeoutId = setTimeout(() => controller.abort(), 60000);

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
        setRoute(data.dijkstra_route.route_points);
        setRouteInfo(data.dijkstra_route);
      } else {
        const errorText = await response.text();
        console.error('Server error:', errorText);
        alert(`ルート比較に失敗しました (${response.status}): ${errorText}`);
      }
    } catch (error) {
      console.error('Route comparison error:', error);
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          alert('リクエストがタイムアウトしました。もう一度お試しください。');
        } else {
          alert(`エラーが発生しました: ${error.message}`);
        }
      } else {
        alert('不明なエラーが発生しました');
      }
    } finally {
      setLoading(false);
    }
  }, [startPoint, endPoint, transportMode]);

  const clearRoute = useCallback(() => {
    setStartPoint(null);
    setEndPoint(null);
    setRoute([]);
    setRouteInfo(null);
  }, []);

  const addCustomNode = useCallback((lat: number, lng: number) => {
    const nodeName = prompt('ノード名を入力してください:', `カスタムポイント ${customNodes.length + 1}`);
    if (!nodeName) return;
    
    const nodeType = prompt('ノードタイプを入力してください:', 'custom') || 'custom';
    const description = prompt('説明を入力してください（任意）:', '');
    
    const newNode: CustomNode = {
      id: `custom-${Date.now()}`,
      lat,
      lng,
      name: nodeName,
      type: nodeType,
      description: description || undefined
    };
    
    setCustomNodes(prev => {
      const updated = [...prev, newNode];
      localStorage.setItem('shade-route-custom-nodes', JSON.stringify(updated));
      return updated;
    });
    setCustomNodeMode(false);
  }, [customNodes.length]);

  const removeCustomNode = useCallback((nodeId: string) => {
    setCustomNodes(prev => {
      const updated = prev.filter(node => node.id !== nodeId);
      localStorage.setItem('shade-route-custom-nodes', JSON.stringify(updated));
      return updated;
    });
  }, []);

  const clearCustomNodes = useCallback(() => {
    if (customNodes.length > 0 && confirm('すべてのカスタムノードを削除しますか？')) {
      setCustomNodes([]);
      localStorage.setItem('shade-route-custom-nodes', JSON.stringify([]));
    }
  }, [customNodes.length]);

  // ルートの色を決定する関数（将来的に使用予定）
  // const getRouteColor = useCallback((shadeRatio: number) => {
  //   if (shadeRatio < 0.25) return '#00FF00'; // 緑
  //   if (shadeRatio < 0.5) return '#FFFF00'; // 黄
  //   if (shadeRatio < 0.75) return '#FF8000'; // オレンジ
  //   return '#FF0000'; // 赤
  // }, []);

  const routeLatLngs = useMemo(() => 
    route.map(point => [point.latitude, point.longitude] as [number, number]),
    [route]
  );

  return (
    <div className="App">
      <header className="app-header">
        <h1>🌳 日陰回避ルート検索</h1>
        <div className="status">
          {customNodeMode && <span>📌 地図をタップしてカスタムノードを追加</span>}
          {!customNodeMode && !startPoint && <span>📍 開始地点をタップしてください</span>}
          {!customNodeMode && startPoint && !endPoint && <span>🎯 終了地点をタップしてください</span>}
          {!customNodeMode && startPoint && endPoint && <span>✅ ルート計算できます</span>}
        </div>
        <div className="controls">
          <select 
            value={transportMode} 
            onChange={(e) => setTransportMode(e.target.value)}
          >
            <option value="walk">徒歩</option>
            <option value="bike">自転車</option>
            <option value="car">車</option>
          </select>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <label>
              <input
                type="checkbox"
                checked={usesDijkstra}
                onChange={(e) => setUsesDijkstra(e.target.checked)}
              />
              ダイクストラ法
            </label>
          </div>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <label>
              <input
                type="checkbox"
                checked={autoUpdate}
                onChange={(e) => setAutoUpdate(e.target.checked)}
              />
              自動更新
            </label>
          </div>
          
          <button onClick={calculateRoute} disabled={!startPoint || !endPoint || loading}>
            {loading ? '計算中...' : usesDijkstra ? '最適ルート計算' : 'ルート計算'}
          </button>
          
          <button onClick={compareRoutes} disabled={!startPoint || !endPoint || loading}>
            {loading ? '計算中...' : '比較'}
          </button>
          
          <button onClick={clearRoute}>クリア</button>
          
          <button 
            onClick={useCallback(() => setShowBuildings(prev => !prev), [])}
            style={{ 
              backgroundColor: showBuildings ? '#ef4444' : '#6b7280',
              color: 'white',
              padding: '0.5rem 1rem',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '1rem'
            }}
          >
            {showBuildings ? '🏢 建物を隠す' : '🏢 建物を表示'}
          </button>
          
          <button 
            onClick={useCallback(() => setHideOSMIcons(prev => !prev), [])}
            style={{ 
              backgroundColor: hideOSMIcons ? '#9333ea' : '#6b7280',
              color: 'white',
              padding: '0.5rem 1rem',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '1rem'
            }}
          >
            {hideOSMIcons ? '🔍 OSMアイコン表示' : '🙈 OSMアイコン隠す'}
          </button>
          
          <button 
            onClick={useCallback(() => setCustomNodeMode(prev => !prev), [])}
            style={{ 
              backgroundColor: customNodeMode ? '#f59e0b' : '#6b7280',
              color: 'white',
              padding: '0.5rem 1rem',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '1rem'
            }}
          >
            {customNodeMode ? '📌 ノード追加中' : '📌 ノード追加'}
          </button>
          
          <button 
            onClick={useCallback(() => setShowCustomNodes(prev => !prev), [])}
            style={{ 
              backgroundColor: showCustomNodes ? '#8b5cf6' : '#6b7280',
              color: 'white',
              padding: '0.5rem 1rem',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '1rem'
            }}
          >
            {showCustomNodes ? '📍 ノード表示中' : '📍 ノード非表示'}
          </button>
          
          {customNodes.length > 0 && (
            <button onClick={clearCustomNodes}>
              🗑️ ノード全削除
            </button>
          )}
          
        </div>
        
        <div className="time-controls">
          <label>
            時刻: 
            <input
              type="time"
              value={selectedTime}
              onChange={(e) => setSelectedTime(e.target.value)}
              style={{ marginLeft: '0.5rem' }}
            />
          </label>
          <span style={{ marginLeft: '1rem', fontSize: '0.9rem', color: '#666' }}>
            {autoUpdate ? '🔄 自動更新ON' : '⏸️ 手動モード'}
          </span>
        </div>
      </header>

      <div className="map-container">
        <MapContainer
          center={[35.6917, 139.7036]} // 新宿駅
          zoom={14}
          style={{ height: '70vh', width: '100%' }}
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
          {showCustomNodes && customNodes.map((node) => (
            <Marker 
              key={node.id} 
              position={[node.lat, node.lng]} 
              icon={customNodeIcon}
            >
              <Popup>
                <div>
                  <strong>{node.name}</strong><br/>
                  タイプ: {node.type}<br/>
                  {node.description && (
                    <>
                      説明: {node.description}<br/>
                    </>
                  )}
                  座標: {node.lat.toFixed(6)}, {node.lng.toFixed(6)}<br/>
                  <button 
                    onClick={() => removeCustomNode(node.id)}
                    style={{ 
                      marginTop: '8px',
                      backgroundColor: '#ef4444',
                      color: 'white',
                      border: 'none',
                      padding: '4px 8px',
                      borderRadius: '4px',
                      cursor: 'pointer'
                    }}
                  >
                    🗑️ 削除
                  </button>
                </div>
              </Popup>
            </Marker>
          ))}

          {route.length > 1 && (
            <Polyline
              positions={routeLatLngs}
              color="#2563eb"
              weight={6}
              opacity={0.8}
            />
          )}

          {/* 建物のポリゴン表示（最適化版） */}
          {showBuildings && buildings.map((building, index) => {
            try {
              const coordinates = building.geometry.coordinates[0];
              const latLngs = coordinates.map(coord => [coord[1], coord[0]] as [number, number]);
              
              // 建物の高さに応じて色を決定
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
                  eventHandlers={{
                    click: () => {
                      console.log('Building clicked:', building.properties.osm_id);
                    }
                  }}
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
      </div>

      {routeInfo && (
        <div className="route-info">
          <h3>ルート情報 {usesDijkstra ? '（ダイクストラ法）' : '（シンプル法）'}</h3>
          <div className="info-grid">
            <div>📏 距離: {Math.round(routeInfo.total_distance)}m</div>
            <div>⏱️ 所要時間: {routeInfo.estimated_time}分</div>
            <div>🌳 平均日陰率: {Math.round(routeInfo.average_shade_ratio * 100)}%</div>
            <div>📍 エリア: {routeInfo.area_name}</div>
            {routeInfo.calculation_time_ms && (
              <div>⚡ 計算時間: {routeInfo.calculation_time_ms}ms</div>
            )}
            {routeInfo.cache_used && (
              <div>💾 キャッシュ使用: 有</div>
            )}
          </div>
          
          <div className="route-features">
            <div className="feature-badge osm">🗺️ HAL東京エリア対応</div>
            <div className="feature-badge building">🏢 実建物データで回避</div>
            <div className="feature-badge shade">🌳 リアルタイム日陰計算</div>
            <div className="feature-badge avoid">🚫 建物貫通防止</div>
            {usesDijkstra && (
              <div className="feature-badge dijkstra">🧮 ダイクストラ法による最適化</div>
            )}
          </div>
        </div>
      )}

      {comparison && (
        <div className="route-comparison">
          <h3>ルート比較結果</h3>
          <div className="comparison-grid">
            <div className="comparison-item">
              <h4>シンプル法</h4>
              <div>📏 距離: {Math.round(comparison.simple_route.total_distance)}m</div>
              <div>⏱️ 時間: {comparison.simple_route.estimated_time}分</div>
              <div>🌳 日陰率: {Math.round(comparison.simple_route.average_shade_ratio * 100)}%</div>
            </div>
            <div className="comparison-item">
              <h4>ダイクストラ法</h4>
              <div>📏 距離: {Math.round(comparison.dijkstra_route.total_distance)}m</div>
              <div>⏱️ 時間: {comparison.dijkstra_route.estimated_time}分</div>
              <div>🌳 日陰率: {Math.round(comparison.dijkstra_route.average_shade_ratio * 100)}%</div>
            </div>
            <div className="comparison-item improvement">
              <h4>改善効果</h4>
              <div style={{ color: comparison.comparison.distance_improvement > 0 ? 'green' : 'red' }}>
                📏 距離: {comparison.comparison.distance_improvement > 0 ? '-' : '+'}
                {Math.abs(Math.round(comparison.comparison.distance_improvement))}m
              </div>
              <div style={{ color: comparison.comparison.shade_improvement > 0 ? 'green' : 'red' }}>
                🌳 日陰率: {comparison.comparison.shade_improvement > 0 ? '+' : ''}
                {Math.round(comparison.comparison.shade_improvement * 100)}%
              </div>
              <div style={{ color: comparison.comparison.time_difference < 0 ? 'green' : 'red' }}>
                ⏱️ 時間: {comparison.comparison.time_difference > 0 ? '+' : ''}
                {comparison.comparison.time_difference}分
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="legend">
        <h4>凡例</h4>
        <div style={{ marginBottom: '1rem' }}>
          <h5 style={{ margin: '0 0 0.5rem 0', color: '#1f2937' }}>日陰率</h5>
          <div className="legend-items">
            <div className="legend-item">
              <div className="legend-color" style={{ backgroundColor: '#00FF00' }}></div>
              <span>低 (0-25%)</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{ backgroundColor: '#FFFF00' }}></div>
              <span>中 (25-50%)</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{ backgroundColor: '#FF8000' }}></div>
              <span>高 (50-75%)</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{ backgroundColor: '#FF0000' }}></div>
              <span>最高 (75%+)</span>
            </div>
          </div>
        </div>
        
        {showBuildings && (
          <div>
            <h5 style={{ margin: '0 0 0.5rem 0', color: '#1f2937' }}>建物の高さ</h5>
            <div className="legend-items">
              <div className="legend-item">
                <div className="legend-color" style={{ backgroundColor: '#10b981' }}></div>
                <span>低層 (~15m)</span>
              </div>
              <div className="legend-item">
                <div className="legend-color" style={{ backgroundColor: '#3b82f6' }}></div>
                <span>中層 (15-30m)</span>
              </div>
              <div className="legend-item">
                <div className="legend-color" style={{ backgroundColor: '#8b5cf6' }}></div>
                <span>高層 (30m+)</span>
              </div>
            </div>
          </div>
        )}
        
      </div>
    </div>
  );
}

export default App;
