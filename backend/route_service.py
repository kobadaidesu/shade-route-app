"""
ルートサービス - 最適化されたルート計算
"""
import asyncio
import hashlib
import logging
import math
import time
from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

from config import map_config, performance_config, transport_config
from cache_manager import cache_manager
from building_service import building_service
from models import RouteRequest, RouteResponse, RoutePoint, TransportMode, WeatherCondition

logger = logging.getLogger(__name__)

class RouteService:
    """ルートサービス"""
    
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=performance_config.max_workers)
    
    def _generate_route_cache_key(self, request: RouteRequest) -> str:
        """ルートリクエストからキャッシュキーを生成"""
        key_data = f"{request.start},{request.end},{request.time},{request.date},{request.transport_mode}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _calculate_distance(self, point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
        """2点間の距離を計算（メートル）"""
        lon1, lat1 = point1
        lon2, lat2 = point2
        
        # Haversine formula
        R = 6371000  # 地球の半径（メートル）
        
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        
        a = (math.sin(dlat/2) * math.sin(dlat/2) +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon/2) * math.sin(dlon/2))
        
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def _calculate_base_shade_ratio(self, lon: float, lat: float, time_str: str) -> float:
        """基本的な日陰率を計算"""
        try:
            hour = int(time_str.split(":")[0])
            
            # 時間帯による基本日陰率
            time_factor = 0.2 + 0.15 * math.sin((hour - 6) * math.pi / 12)
            
            # 位置による調整（新宿エリア中心）
            center_lon, center_lat = map_config.shinjuku_station_location[1], map_config.shinjuku_station_location[0]
            position_factor = ((lat - center_lat) * 2 + (lon - center_lon) * 0.5) * 0.1
            
            # 総合日陰率
            total_shade = max(0.0, min(1.0, time_factor + position_factor))
            return total_shade
            
        except Exception as e:
            logger.error(f"Base shade calculation error: {e}")
            return 0.3
    
    async def _calculate_shade_ratio(self, 
                                   lon: float, 
                                   lat: float, 
                                   time_str: str, 
                                   buildings: List) -> float:
        """日陰率を計算（建物の影を考慮）"""
        try:
            # 建物内部の場合は通行不可
            if building_service.is_point_in_building(lon, lat, buildings):
                return 0.0
            
            # 基本的な日陰率
            base_shade = self._calculate_base_shade_ratio(lon, lat, time_str)
            
            # 建物による影の計算
            loop = asyncio.get_event_loop()
            shadow_factor = await loop.run_in_executor(
                self.executor,
                building_service.calculate_shadow_factor,
                lon, lat, time_str, buildings
            )
            
            # 総合日陰率
            total_shade = min(1.0, base_shade + shadow_factor)
            return total_shade
            
        except Exception as e:
            logger.error(f"Shade ratio calculation error: {e}")
            return 0.3
    
    def _line_intersects_buildings(self, 
                                 start_lon: float, start_lat: float,
                                 end_lon: float, end_lat: float,
                                 buildings: List) -> bool:
        """線分が建物と交差するかチェック"""
        steps = 5  # パフォーマンス向上のため段数を削減
        
        for i in range(steps + 1):
            ratio = i / steps
            check_lon = start_lon + (end_lon - start_lon) * ratio
            check_lat = start_lat + (end_lat - start_lat) * ratio
            
            if building_service.is_point_in_building(check_lon, check_lat, buildings):
                return True
        
        return False
    
    def _find_detour_point(self, 
                          start_lon: float, start_lat: float,
                          target_lon: float, target_lat: float,
                          buildings: List) -> Optional[Tuple[float, float]]:
        """迂回ポイントを見つける"""
        detour_distance = map_config.building_search_radius
        
        # 迂回候補（効率化のため数を削減）
        detour_options = [
            (target_lon, target_lat + detour_distance),     # 北
            (target_lon, target_lat - detour_distance),     # 南
            (target_lon + detour_distance, target_lat),     # 東
            (target_lon - detour_distance, target_lat),     # 西
        ]
        
        best_point = None
        min_distance = float('inf')
        
        for detour_lon, detour_lat in detour_options:
            # 迂回ポイントが建物内でないかチェック
            if not building_service.is_point_in_building(detour_lon, detour_lat, buildings):
                # 迂回ポイントへの線分が建物と交差しないかチェック
                if not self._line_intersects_buildings(start_lon, start_lat, detour_lon, detour_lat, buildings):
                    # 目標地点に最も近い迂回ポイントを選択
                    distance = math.sqrt((detour_lon - target_lon) ** 2 + (detour_lat - target_lat) ** 2)
                    if distance < min_distance:
                        min_distance = distance
                        best_point = (detour_lon, detour_lat)
        
        return best_point
    
    async def _generate_route_points(self, 
                                   start_lon: float, start_lat: float,
                                   end_lon: float, end_lat: float,
                                   buildings: List) -> List[Tuple[float, float]]:
        """建物を避けるルートポイントを生成"""
        route_points = [(start_lon, start_lat)]
        num_segments = performance_config.route_points_count
        
        for i in range(1, num_segments + 1):
            ratio = i / num_segments
            
            # 基本の直線ルート
            target_lon = start_lon + (end_lon - start_lon) * ratio
            target_lat = start_lat + (end_lat - start_lat) * ratio
            
            # 前のポイントから現在のポイントへの線分をチェック
            prev_lon, prev_lat = route_points[-1]
            
            # 線分が建物と交差するかチェック
            if self._line_intersects_buildings(prev_lon, prev_lat, target_lon, target_lat, buildings):
                # 建物回避のための迂回ポイントを探す
                detour_point = self._find_detour_point(prev_lon, prev_lat, target_lon, target_lat, buildings)
                
                if detour_point:
                    route_points.append(detour_point)
                else:
                    # 迂回が見つからない場合は大きく迂回
                    detour_distance = map_config.building_search_radius * 2
                    fallback_point = (target_lon, target_lat + detour_distance)
                    route_points.append(fallback_point)
            else:
                # 建物との交差なし
                route_points.append((target_lon, target_lat))
        
        # 最終地点を確実に追加
        if route_points[-1] != (end_lon, end_lat):
            route_points.append((end_lon, end_lat))
        
        return route_points
    
    async def calculate_route(self, request: RouteRequest) -> RouteResponse:
        """ルートを計算"""
        start_time = time.time()
        
        # キャッシュチェック
        cache_key = self._generate_route_cache_key(request)
        cached_route = cache_manager.get_route(cache_key)
        
        if cached_route:
            logger.info("Using cached route data")
            cached_route["cache_used"] = True
            return RouteResponse(**cached_route)
        
        try:
            start_lon, start_lat = request.start
            end_lon, end_lat = request.end
            
            # 建物データを取得
            buildings_collection = await building_service.get_buildings()
            buildings = buildings_collection.features
            
            # 建物を避けるルートポイントを生成
            route_coordinates = await self._generate_route_points(
                start_lon, start_lat, end_lon, end_lat, buildings
            )
            
            # 並列処理で日陰率を計算
            shade_tasks = []
            for lon, lat in route_coordinates:
                task = self._calculate_shade_ratio(lon, lat, request.time, buildings)
                shade_tasks.append(task)
            
            shade_ratios = await asyncio.gather(*shade_tasks)
            
            # RoutePointオブジェクトを作成
            route_points = []
            for i, (lon, lat) in enumerate(route_coordinates):
                route_points.append(RoutePoint(
                    longitude=lon,
                    latitude=lat,
                    shade_ratio=shade_ratios[i]
                ))
            
            # 距離計算
            total_distance = 0
            for i in range(len(route_points) - 1):
                p1 = route_points[i]
                p2 = route_points[i + 1]
                distance = self._calculate_distance(
                    (p1.longitude, p1.latitude),
                    (p2.longitude, p2.latitude)
                )
                total_distance += distance
            
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
                area_name="新宿区〜HAL東京",
                weather_condition=WeatherCondition.PARTLY_CLOUDY,
                cache_used=False,
                calculation_time_ms=calculation_time
            )
            
            # キャッシュに保存
            cache_manager.set_route(cache_key, response.dict())
            
            logger.info(f"Route calculated in {calculation_time}ms with {len(route_points)} points")
            
            return response
            
        except Exception as e:
            logger.error(f"Route calculation error: {e}")
            raise

# グローバルサービスインスタンス
route_service = RouteService()