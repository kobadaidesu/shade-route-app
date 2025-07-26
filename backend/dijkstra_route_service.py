"""
ダイクストラ法によるルート探索サービス
"""
import asyncio
import hashlib
import logging
import math
import time
from typing import List, Optional, Tuple, Dict

from config import map_config, performance_config, transport_config
from cache_manager import cache_manager
from building_service import building_service
from grid_map import GridMap, DijkstraPathfinder, get_grid_map, GridCell
from models import RouteRequest, RouteResponse, RoutePoint, TransportMode, WeatherCondition

logger = logging.getLogger(__name__)

class DijkstraRouteService:
    """ダイクストラ法によるルート探索サービス"""
    
    def __init__(self):
        self.grid_size = 0.0003  # 約30m（より大きなグリッドで直線的に）
        self.pathfinder_cache = {}
    
    def _generate_dijkstra_cache_key(self, request: RouteRequest) -> str:
        """ダイクストラ法用のキャッシュキーを生成"""
        key_data = f"dijkstra_{request.start},{request.end},{request.time},{request.date},{request.transport_mode}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _calculate_grid_bbox(self, start_coord: Tuple[float, float], 
                           end_coord: Tuple[float, float]) -> Tuple[float, float, float, float]:
        """グリッドの境界ボックスを計算"""
        start_lon, start_lat = start_coord
        end_lon, end_lat = end_coord
        
        # 余裕をもたせた境界ボックス
        margin = 0.002  # 約200m
        
        min_lon = min(start_lon, end_lon) - margin
        max_lon = max(start_lon, end_lon) + margin
        min_lat = min(start_lat, end_lat) - margin
        max_lat = max(start_lat, end_lat) + margin
        
        return (min_lat, min_lon, max_lat, max_lon)  # south, west, north, east
    
    def _calculate_shade_weights(self, transport_mode: TransportMode) -> Tuple[float, float]:
        """交通手段に応じた重みを計算（日陰を重視するため重み上げ）"""
        weight_configs = {
            TransportMode.WALK: (0.6, 0.4),    # 歩行者は日陰を重視
            TransportMode.RUN: (0.7, 0.3),     # ランニングは日陰を最重視
            TransportMode.BIKE: (0.5, 0.5),    # 自転車は日陰と距離のバランス
            TransportMode.CAR: (0.2, 0.8)      # 車は距離重視
        }
        
        return weight_configs.get(transport_mode, (0.6, 0.4))
    
    def _grid_path_to_route_points(self, grid_path: List[GridCell], 
                                  time_str: str) -> List[RoutePoint]:
        """グリッドパスをルートポイントに変換"""
        route_points = []
        
        for cell in grid_path:
            # 日陰率を計算（コストから逆算）
            shade_ratio = max(0.0, 1.0 - cell.shade_cost)
            
            route_point = RoutePoint(
                longitude=cell.lon,
                latitude=cell.lat,
                shade_ratio=shade_ratio
            )
            route_points.append(route_point)
        
        return route_points
    
    def _calculate_total_distance(self, route_points: List[RoutePoint]) -> float:
        """総距離を計算"""
        total_distance = 0.0
        
        for i in range(len(route_points) - 1):
            p1 = route_points[i]
            p2 = route_points[i + 1]
            
            # Haversine formula for accurate distance
            R = 6371000  # Earth's radius in meters
            
            lat1, lon1 = p1.latitude, p1.longitude
            lat2, lon2 = p2.latitude, p2.longitude
            
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            
            a = (math.sin(dlat/2) * math.sin(dlat/2) +
                 math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
                 math.sin(dlon/2) * math.sin(dlon/2))
            
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            distance = R * c
            
            total_distance += distance
        
        return total_distance
    
    async def calculate_optimal_route(self, request: RouteRequest) -> RouteResponse:
        """ダイクストラ法で最適ルートを計算"""
        start_time = time.time()
        
        # キャッシュチェック
        cache_key = self._generate_dijkstra_cache_key(request)
        cached_route = cache_manager.get_route(cache_key)
        
        if cached_route:
            logger.info("Using cached Dijkstra route")
            cached_route["cache_used"] = True
            return RouteResponse(**cached_route)
        
        try:
            start_lon, start_lat = request.start
            end_lon, end_lat = request.end
            
            # グリッドの境界ボックスを計算
            bbox = self._calculate_grid_bbox(
                (start_lon, start_lat), 
                (end_lon, end_lat)
            )
            
            # グリッドマップを取得
            grid_map = get_grid_map(bbox, self.grid_size)
            
            # 建物データを取得してグリッドを更新
            buildings_collection = await building_service.get_buildings(bbox)
            buildings = buildings_collection.features
            
            await grid_map.update_with_buildings(buildings, request.time)
            
            # ダイクストラ法でパスを探索
            pathfinder = DijkstraPathfinder(grid_map)
            weight_shade, weight_distance = self._calculate_shade_weights(request.transport_mode)
            
            grid_path = pathfinder.find_path(
                start_coord=(start_lon, start_lat),
                end_coord=(end_lon, end_lat),
                weight_shade=weight_shade,
                weight_distance=weight_distance
            )
            
            if not grid_path:
                raise ValueError("No path found using Dijkstra algorithm")
            
            # パスをスムージング（より積極的に）
            smoothed_path = pathfinder.smooth_path(grid_path, smoothing_factor=8)
            
            # さらにポイントを減らす（最大20ポイント）
            if len(smoothed_path) > 20:
                step = len(smoothed_path) // 20
                reduced_path = [smoothed_path[i] for i in range(0, len(smoothed_path), step)]
                if reduced_path[-1] != smoothed_path[-1]:
                    reduced_path.append(smoothed_path[-1])
                smoothed_path = reduced_path
            
            # ルートポイントに変換
            route_points = self._grid_path_to_route_points(smoothed_path, request.time)
            
            # 距離計算
            total_distance = self._calculate_total_distance(route_points)
            
            # 平均日陰率
            avg_shade = sum(p.shade_ratio for p in route_points) / len(route_points)
            
            # 所要時間計算
            speed = transport_config.speed_map.get(request.transport_mode.value, 5.0)
            estimated_time = max(1, int((total_distance / 1000) / speed * 60))
            
            # 計算時間
            calculation_time = int((time.time() - start_time) * 1000)
            
            # レスポンス作成
            response = RouteResponse(
                route_points=route_points,
                total_distance=total_distance,
                estimated_time=estimated_time,
                average_shade_ratio=avg_shade,
                transport_mode=request.transport_mode,
                area_name=f"新宿区（ダイクストラ法: {len(route_points)}点）",
                weather_condition=WeatherCondition.PARTLY_CLOUDY,
                cache_used=False,
                calculation_time_ms=calculation_time
            )
            
            # キャッシュに保存
            cache_manager.set_route(cache_key, response.dict())
            
            logger.info(f"Dijkstra route calculated in {calculation_time}ms with {len(route_points)} points")
            logger.info(f"Grid size: {grid_map.grid_width}x{grid_map.grid_height}, "
                       f"Weights: shade={weight_shade:.2f}, distance={weight_distance:.2f}")
            
            return response
            
        except Exception as e:
            logger.error(f"Dijkstra route calculation error: {e}")
            raise
    
    async def compare_routes(self, request: RouteRequest) -> Dict[str, RouteResponse]:
        """既存の方法とダイクストラ法を比較"""
        from route_service import route_service
        
        # 両方の方法で計算
        try:
            simple_route = await route_service.calculate_route(request)
            dijkstra_route = await self.calculate_optimal_route(request)
            
            return {
                "simple_route": simple_route,
                "dijkstra_route": dijkstra_route,
                "comparison": {
                    "distance_improvement": simple_route.total_distance - dijkstra_route.total_distance,
                    "shade_improvement": dijkstra_route.average_shade_ratio - simple_route.average_shade_ratio,
                    "time_difference": dijkstra_route.estimated_time - simple_route.estimated_time
                }
            }
        except Exception as e:
            logger.error(f"Route comparison error: {e}")
            raise

# グローバルサービスインスタンス
dijkstra_route_service = DijkstraRouteService()