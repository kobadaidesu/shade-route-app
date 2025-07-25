"""
設定ファイル - パフォーマンスとコード品質の改善
"""
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass
class APIConfig:
    """API関連の設定"""
    host: str = "0.0.0.0"
    port: int = 8006
    title: str = "Shade Route API"
    version: str = "2.0.0"
    
    # CORS設定
    cors_origins: List[str] = None
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = None
    cors_allow_headers: List[str] = None
    
    def __post_init__(self):
        if self.cors_origins is None:
            self.cors_origins = ["http://localhost:3000", "http://localhost:5173", "http://localhost:5174"]
        if self.cors_allow_methods is None:
            self.cors_allow_methods = ["GET", "POST", "PUT", "DELETE"]
        if self.cors_allow_headers is None:
            self.cors_allow_headers = ["*"]

@dataclass
class CacheConfig:
    """キャッシュ関連の設定"""
    max_cache_size: int = 10  # 最大キャッシュアイテム数
    cache_ttl_seconds: int = 3600  # キャッシュの有効期限（1時間）
    building_cache_enabled: bool = True
    route_cache_enabled: bool = True

@dataclass
class MapConfig:
    """地図関連の設定"""
    # 東京の境界ボックス (south, west, north, east)
    tokyo_bbox: Tuple[float, float, float, float] = (35.6, 139.6, 35.8, 139.8)
    
    # 新宿エリアの境界ボックス（デフォルト）
    shinjuku_bbox: Tuple[float, float, float, float] = (35.685, 139.695, 35.705, 139.715)
    
    # HAL東京の座標
    hal_tokyo_location: Tuple[float, float] = (35.6948, 139.7039)
    
    # 新宿駅の座標
    shinjuku_station_location: Tuple[float, float] = (35.6917, 139.7036)
    
    # 建物検索の最大距離（度）
    building_search_radius: float = 0.001  # 約100m
    
    # 影計算の最大距離（度）
    shadow_max_distance: float = 0.0005  # 約50m

@dataclass
class PerformanceConfig:
    """パフォーマンス関連の設定"""
    # ルートポイントの数
    route_points_count: int = 20
    
    # 並列処理の最大ワーカー数
    max_workers: int = 4
    
    # 外部API呼び出しのタイムアウト（秒）
    external_api_timeout: int = 30
    
    # リクエストの最大待機時間（秒）
    max_request_timeout: int = 60
    
    # 建物データの最大取得数
    max_buildings_per_request: int = 1000

@dataclass
class TransportConfig:
    """交通手段の設定"""
    speed_map: Dict[str, float] = None  # km/h
    
    def __post_init__(self):
        if self.speed_map is None:
            self.speed_map = {
                "walk": 5.0,
                "bike": 15.0,
                "car": 30.0,
                "run": 8.0
            }

@dataclass
class OSMConfig:
    """OpenStreetMap関連の設定"""
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    backup_overpass_urls: List[str] = None
    
    def __post_init__(self):
        if self.backup_overpass_urls is None:
            self.backup_overpass_urls = [
                "https://overpass.kumi.systems/api/interpreter",
                "https://overpass.openstreetmap.ru/api/interpreter"
            ]

# 設定インスタンス
api_config = APIConfig()
cache_config = CacheConfig()
map_config = MapConfig()
performance_config = PerformanceConfig()
transport_config = TransportConfig()
osm_config = OSMConfig()

# 環境変数からの設定上書き
def load_config_from_env():
    """環境変数から設定を読み込む"""
    if os.getenv("API_PORT"):
        api_config.port = int(os.getenv("API_PORT"))
    
    if os.getenv("CACHE_TTL"):
        cache_config.cache_ttl_seconds = int(os.getenv("CACHE_TTL"))
    
    if os.getenv("MAX_WORKERS"):
        performance_config.max_workers = int(os.getenv("MAX_WORKERS"))
    
    if os.getenv("CORS_ORIGINS"):
        api_config.cors_origins = os.getenv("CORS_ORIGINS").split(",")

# 初期化時に環境変数を読み込む
load_config_from_env()