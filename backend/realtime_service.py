"""
リアルタイム日陰更新サービス
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from building_service import building_service
from grid_map import GridMap, get_grid_map
from models import RoutePoint, Building

logger = logging.getLogger(__name__)

@dataclass
class ShadePrediction:
    """日陰予測データ"""
    time: str
    shade_ratio: float
    sun_elevation: float
    sun_azimuth: float

@dataclass
class RealtimeShadeData:
    """リアルタイム日陰データ"""
    current_time: str
    predictions: List[ShadePrediction]
    next_update: str

class RealtimeShadeService:
    """リアルタイム日陰サービス"""
    
    def __init__(self):
        self.update_interval = 300  # 5分間隔
        self.cache_duration = 3600  # 1時間キャッシュ
        self.shade_cache: Dict[str, RealtimeShadeData] = {}
        self.last_update_time = 0
        
    def _calculate_sun_position(self, time_str: str) -> Tuple[float, float]:
        """太陽位置を計算"""
        try:
            hour = int(time_str.split(":")[0])
            minute = int(time_str.split(":")[1])
            decimal_hour = hour + minute / 60.0
            
            # 太陽高度角（正午で最高、日の出・日没で最低）
            sun_elevation = max(5, 90 - abs(decimal_hour - 12) * 7.5)
            
            # 太陽方位角（東から西へ）
            sun_azimuth = (decimal_hour - 12) * 15  # 1時間で15度回転
            
            return sun_elevation, sun_azimuth
        except:
            return 45.0, 0.0  # デフォルト値
    
    def _calculate_shade_for_time(self, lon: float, lat: float, 
                                 time_str: str, buildings: List[Building]) -> float:
        """指定時刻の日陰率を計算"""
        try:
            # 建物内部の場合
            if building_service.is_point_in_building(lon, lat, buildings):
                return 0.0
            
            # 建物による影の計算
            shadow_factor = building_service.calculate_shadow_factor(
                lon, lat, time_str, buildings
            )
            
            # 基本的な日陰率
            hour = int(time_str.split(":")[0])
            base_shade = 0.2 + 0.15 * (1 - abs(hour - 12) / 12)  # 正午で最低
            
            # 総合日陰率
            total_shade = min(1.0, shadow_factor + base_shade)
            return total_shade
            
        except Exception as e:
            logger.error(f"Shade calculation error: {e}")
            return 0.3
    
    async def get_hourly_predictions(self, lon: float, lat: float, 
                                   date: str = None) -> List[ShadePrediction]:
        """1日の時間別日陰予測を取得"""
        try:
            if date is None:
                date = datetime.now().strftime("%Y-%m-%d")
            
            # キャッシュキーを生成
            cache_key = f"{lon:.6f}_{lat:.6f}_{date}"
            
            # キャッシュをチェック
            if cache_key in self.shade_cache:
                cached_data = self.shade_cache[cache_key]
                cache_time = datetime.fromisoformat(cached_data.current_time)
                if (datetime.now() - cache_time).seconds < self.cache_duration:
                    return cached_data.predictions
            
            # 建物データを取得
            # 点の周辺の境界ボックスを計算
            margin = 0.002  # 約200m
            bbox = (lat - margin, lon - margin, lat + margin, lon + margin)
            
            buildings_collection = await building_service.get_buildings(bbox)
            buildings = buildings_collection.features
            
            # 1日の予測を生成（6時から20時まで）
            predictions = []
            for hour in range(6, 21):
                time_str = f"{hour:02d}:00"
                
                # 太陽位置を計算
                sun_elevation, sun_azimuth = self._calculate_sun_position(time_str)
                
                # 日陰率を計算
                shade_ratio = self._calculate_shade_for_time(lon, lat, time_str, buildings)
                
                prediction = ShadePrediction(
                    time=time_str,
                    shade_ratio=shade_ratio,
                    sun_elevation=sun_elevation,
                    sun_azimuth=sun_azimuth
                )
                predictions.append(prediction)
            
            # キャッシュに保存
            realtime_data = RealtimeShadeData(
                current_time=datetime.now().isoformat(),
                predictions=predictions,
                next_update=(datetime.now() + timedelta(minutes=5)).isoformat()
            )
            self.shade_cache[cache_key] = realtime_data
            
            return predictions
            
        except Exception as e:
            logger.error(f"Hourly predictions error: {e}")
            return []
    
    async def get_route_shade_timeline(self, route_points: List[RoutePoint], 
                                     date: str = None) -> Dict[str, List[float]]:
        """ルート全体の時間別日陰変化を取得"""
        try:
            if not route_points:
                return {}
            
            if date is None:
                date = datetime.now().strftime("%Y-%m-%d")
            
            # 建物データを取得（ルート全体をカバー）
            lons = [p.longitude for p in route_points]
            lats = [p.latitude for p in route_points]
            margin = 0.002
            
            bbox = (
                min(lats) - margin,
                min(lons) - margin,
                max(lats) + margin,
                max(lons) + margin
            )
            
            buildings_collection = await building_service.get_buildings(bbox)
            buildings = buildings_collection.features
            
            # 時間別の日陰率を計算
            timeline = {}
            
            for hour in range(6, 21):
                time_str = f"{hour:02d}:00"
                hourly_shades = []
                
                for point in route_points:
                    shade_ratio = self._calculate_shade_for_time(
                        point.longitude, point.latitude, time_str, buildings
                    )
                    hourly_shades.append(shade_ratio)
                
                timeline[time_str] = hourly_shades
            
            return timeline
            
        except Exception as e:
            logger.error(f"Route shade timeline error: {e}")
            return {}
    
    async def get_current_shade_update(self, lon: float, lat: float) -> Dict:
        """現在の日陰情報を取得"""
        try:
            current_time = datetime.now()
            time_str = current_time.strftime("%H:%M")
            
            # 建物データを取得
            margin = 0.001
            bbox = (lat - margin, lon - margin, lat + margin, lon + margin)
            
            buildings_collection = await building_service.get_buildings(bbox)
            buildings = buildings_collection.features
            
            # 現在の日陰率
            current_shade = self._calculate_shade_for_time(lon, lat, time_str, buildings)
            
            # 太陽位置
            sun_elevation, sun_azimuth = self._calculate_sun_position(time_str)
            
            # 次の更新時間
            next_update = current_time + timedelta(minutes=5)
            
            return {
                "current_time": time_str,
                "current_shade_ratio": current_shade,
                "sun_elevation": sun_elevation,
                "sun_azimuth": sun_azimuth,
                "next_update": next_update.strftime("%H:%M"),
                "update_interval_minutes": 5
            }
            
        except Exception as e:
            logger.error(f"Current shade update error: {e}")
            return {
                "current_time": datetime.now().strftime("%H:%M"),
                "current_shade_ratio": 0.3,
                "sun_elevation": 45.0,
                "sun_azimuth": 0.0,
                "next_update": (datetime.now() + timedelta(minutes=5)).strftime("%H:%M"),
                "update_interval_minutes": 5
            }
    
    def cleanup_cache(self):
        """期限切れキャッシュをクリーンアップ"""
        try:
            current_time = datetime.now()
            expired_keys = []
            
            for key, data in self.shade_cache.items():
                cache_time = datetime.fromisoformat(data.current_time)
                if (current_time - cache_time).seconds > self.cache_duration:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.shade_cache[key]
            
            logger.info(f"Cleaned up {len(expired_keys)} expired shade cache entries")
            
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")

# グローバルサービスインスタンス
realtime_shade_service = RealtimeShadeService()