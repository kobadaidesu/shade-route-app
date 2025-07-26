"""
建物サービス - 最適化された建物データ処理
"""
import asyncio
import logging
import math
import time
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import aiohttp
import hashlib

from config import osm_config, map_config, performance_config
from cache_manager import cache_manager
from models import Building, BuildingCollection, BuildingProperties, BuildingGeometry

logger = logging.getLogger(__name__)

class BuildingService:
    """建物サービス"""
    
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=performance_config.max_workers)
        self._session = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """HTTPセッションを取得"""
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=performance_config.external_api_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """リソースのクリーンアップ"""
        if self._session:
            await self._session.close()
            self._session = None
    
    def _generate_cache_key(self, bbox: Tuple[float, float, float, float]) -> str:
        """境界ボックスからキャッシュキーを生成"""
        bbox_str = f"{bbox[0]:.6f},{bbox[1]:.6f},{bbox[2]:.6f},{bbox[3]:.6f}"
        return hashlib.md5(bbox_str.encode()).hexdigest()
    
    def _create_overpass_query(self, bbox: Tuple[float, float, float, float]) -> str:
        """Overpassクエリを生成（最適化版 - 新宿区全域対応）"""
        return f"""
        [out:json][timeout:{performance_config.external_api_timeout}][maxsize:1073741824];
        (
          way[building]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
          relation[building]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
          way[building:part]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
        );
        out geom {performance_config.max_buildings_per_request};
        """
    
    async def _fetch_from_overpass(self, query: str, url: str) -> Optional[Dict]:
        """Overpass APIからデータを取得"""
        try:
            session = await self._get_session()
            async with session.post(url, data=query) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"Overpass API error: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Overpass API request failed: {e}")
            return None
    
    async def _fetch_buildings_from_osm(self, bbox: Tuple[float, float, float, float]) -> Optional[Dict]:
        """OSMから建物データを取得（バックアップURL対応）"""
        query = self._create_overpass_query(bbox)
        
        # メインURLを試行
        osm_data = await self._fetch_from_overpass(query, osm_config.overpass_url)
        if osm_data:
            return osm_data
        
        # バックアップURLを試行
        for backup_url in osm_config.backup_overpass_urls:
            logger.info(f"Trying backup URL: {backup_url}")
            osm_data = await self._fetch_from_overpass(query, backup_url)
            if osm_data:
                return osm_data
        
        return None
    
    def _estimate_building_height(self, tags: Dict) -> float:
        """建物の高さを推定"""
        # 高さタグから直接取得
        if "height" in tags:
            try:
                height_str = str(tags["height"]).replace("m", "").replace("ft", "")
                height = float(height_str)
                if "ft" in str(tags["height"]):
                    height = height * 0.3048  # フィートからメートルに変換
                return max(3.0, height)
            except (ValueError, TypeError):
                pass
        
        # 階数から推定
        if "building:levels" in tags:
            try:
                levels = int(tags["building:levels"])
                return max(3.0, levels * 3.5)  # 1階=3.5m想定
            except (ValueError, TypeError):
                pass
        
        # 建物タイプから推定
        building_type = tags.get("building", "")
        height_map = {
            "skyscraper": 100.0,
            "office": 50.0,
            "apartments": 30.0,
            "commercial": 20.0,
            "hotel": 40.0,
            "hospital": 25.0,
            "school": 15.0,
            "house": 8.0,
            "garage": 4.0,
            "shed": 3.0
        }
        
        return height_map.get(building_type, 10.0)
    
    def _process_building_element(self, element: Dict) -> Optional[Building]:
        """建物要素を処理"""
        try:
            if element.get("type") != "way" or "geometry" not in element:
                return None
            
            coordinates = [[coord["lon"], coord["lat"]] for coord in element["geometry"]]
            if len(coordinates) < 3:
                return None
            
            # 閉じた多角形にする
            if coordinates[0] != coordinates[-1]:
                coordinates.append(coordinates[0])
            
            # 建物情報を取得
            tags = element.get("tags", {})
            height = self._estimate_building_height(tags)
            
            building = Building(
                geometry=BuildingGeometry(
                    type="Polygon",
                    coordinates=[coordinates]
                ),
                properties=BuildingProperties(
                    building=tags.get("building", "yes"),
                    height=height,
                    osm_id=element.get("id"),
                    levels=tags.get("building:levels")
                )
            )
            
            return building
            
        except Exception as e:
            logger.warning(f"Building processing error: {e}")
            return None
    
    async def get_buildings(self, bbox: Optional[Tuple[float, float, float, float]] = None) -> BuildingCollection:
        """建物データを取得"""
        if bbox is None:
            bbox = map_config.shinjuku_bbox
        
        cache_key = self._generate_cache_key(bbox)
        
        # キャッシュから取得を試行
        cached_data = cache_manager.get_buildings(cache_key)
        if cached_data:
            logger.info(f"Using cached building data for bbox: {bbox}")
            return BuildingCollection(**cached_data)
        
        start_time = time.time()
        logger.info(f"Fetching building data from OSM for bbox: {bbox}")
        
        try:
            # OSMからデータを取得
            osm_data = await self._fetch_buildings_from_osm(bbox)
            if not osm_data:
                logger.error("Failed to fetch building data from all sources")
                return BuildingCollection(features=[])
            
            # 並列処理で建物データを処理
            loop = asyncio.get_event_loop()
            elements = osm_data.get("elements", [])
            
            # 建物数を制限
            if len(elements) > performance_config.max_buildings_per_request:
                elements = elements[:performance_config.max_buildings_per_request]
                logger.warning(f"Limited buildings to {performance_config.max_buildings_per_request}")
            
            # 並列処理でビルディングを処理
            tasks = []
            for element in elements:
                task = loop.run_in_executor(
                    self.executor,
                    self._process_building_element,
                    element
                )
                tasks.append(task)
            
            buildings = await asyncio.gather(*tasks)
            buildings = [b for b in buildings if b is not None]
            
            building_collection = BuildingCollection(features=buildings)
            
            # キャッシュに保存
            cache_manager.set_buildings(cache_key, building_collection.dict())
            
            processing_time = time.time() - start_time
            logger.info(f"Processed {len(buildings)} buildings in {processing_time:.2f}s")
            
            return building_collection
            
        except Exception as e:
            logger.error(f"Building data processing error: {e}")
            return BuildingCollection(features=[])
    
    def calculate_shadow_factor(self, 
                              point_lon: float, 
                              point_lat: float, 
                              time_str: str, 
                              buildings: List[Building]) -> float:
        """効率的な影計算"""
        try:
            hour = int(time_str.split(":")[0])
            
            # 夜間は完全な日陰（100%）
            if hour < 6 or hour > 18:
                return 1.0
            
            # 太陽角度計算（日中のみ）
            sun_elevation = max(0, 90 - abs(hour - 12) * 7.5)
            sun_azimuth = (hour - 12) * 15
            
            # 太陽高度が0以下の場合は完全な日陰
            if sun_elevation <= 0:
                return 1.0
            
            max_shadow_factor = 0.0
            
            # 効率的な範囲フィルタリング
            for building in buildings:
                try:
                    coords = building.geometry.coordinates[0]
                    height = building.properties.height
                    
                    # 建物の中心座標を計算
                    center_lon = sum(c[0] for c in coords) / len(coords)
                    center_lat = sum(c[1] for c in coords) / len(coords)
                    
                    # 距離チェック（効率化のため）
                    distance = math.sqrt((point_lon - center_lon) ** 2 + (point_lat - center_lat) ** 2)
                    
                    # 影響範囲外の場合はスキップ
                    shadow_length_degrees = (height / 111000) / math.tan(math.radians(sun_elevation))
                    if distance > shadow_length_degrees * 1.5:
                        continue
                    
                    # 影の計算
                    shadow_direction = math.radians(sun_azimuth + 180)
                    shadow_end_lon = center_lon + shadow_length_degrees * math.cos(shadow_direction)
                    shadow_end_lat = center_lat + shadow_length_degrees * math.sin(shadow_direction)
                    
                    # ポイントが影の範囲内かチェック
                    shadow_distance = math.sqrt((point_lon - shadow_end_lon) ** 2 + (point_lat - shadow_end_lat) ** 2)
                    
                    if shadow_distance < shadow_length_degrees * 0.6:
                        building_shadow = min(0.9, height / 40.0)
                        max_shadow_factor = max(max_shadow_factor, building_shadow)
                    
                except Exception as e:
                    logger.debug(f"Shadow calculation error for building: {e}")
                    continue
            
            return min(1.0, max_shadow_factor)
            
        except Exception as e:
            logger.error(f"Shadow calculation error: {e}")
            return 0.0
    
    def is_point_in_building(self, 
                           point_lon: float, 
                           point_lat: float, 
                           buildings: List[Building]) -> bool:
        """ポイントが建物内にあるかチェック（最適化版）"""
        for building in buildings:
            try:
                coords = building.geometry.coordinates[0]
                
                # 粗い境界チェック
                min_lon = min(c[0] for c in coords)
                max_lon = max(c[0] for c in coords)
                min_lat = min(c[1] for c in coords)
                max_lat = max(c[1] for c in coords)
                
                if not (min_lon <= point_lon <= max_lon and min_lat <= point_lat <= max_lat):
                    continue
                
                # Ray casting algorithm
                inside = False
                j = len(coords) - 1
                
                for i in range(len(coords)):
                    if ((coords[i][1] > point_lat) != (coords[j][1] > point_lat)) and \
                       (point_lon < (coords[j][0] - coords[i][0]) * (point_lat - coords[i][1]) / (coords[j][1] - coords[i][1]) + coords[i][0]):
                        inside = not inside
                    j = i
                
                if inside:
                    return True
                    
            except Exception as e:
                logger.debug(f"Point in building check error: {e}")
                continue
        
        return False

# グローバルサービスインスタンス
building_service = BuildingService()