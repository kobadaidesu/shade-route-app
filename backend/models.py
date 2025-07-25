"""
データモデル - 型安全性とバリデーション強化
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator
from enum import Enum
import re

class TransportMode(str, Enum):
    """交通手段の列挙型"""
    WALK = "walk"
    BIKE = "bike"
    CAR = "car"
    RUN = "run"

class WeatherCondition(str, Enum):
    """天気の列挙型"""
    SUNNY = "sunny"
    PARTLY_CLOUDY = "partly_cloudy"
    CLOUDY = "cloudy"
    RAINY = "rainy"

class RouteRequest(BaseModel):
    """ルートリクエスト"""
    start: List[float] = Field(..., description="開始地点の座標 [longitude, latitude]")
    end: List[float] = Field(..., description="終了地点の座標 [longitude, latitude]")
    time: str = Field(..., description="時刻 (HH:MM形式)")
    date: str = Field(..., description="日付 (YYYY-MM-DD形式)")
    transport_mode: TransportMode = Field(default=TransportMode.WALK, description="交通手段")
    
    @validator('start', 'end')
    def validate_coordinates(cls, v):
        """座標の妥当性チェック"""
        if len(v) != 2:
            raise ValueError('座標は [longitude, latitude] の形式で指定してください')
        
        lon, lat = v
        if not (-180 <= lon <= 180):
            raise ValueError('経度は -180 から 180 の範囲で指定してください')
        if not (-90 <= lat <= 90):
            raise ValueError('緯度は -90 から 90 の範囲で指定してください')
        
        return v
    
    @validator('time')
    def validate_time(cls, v):
        """時刻の妥当性チェック"""
        if not re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', v):
            raise ValueError('時刻は HH:MM 形式で指定してください')
        return v
    
    @validator('date')
    def validate_date(cls, v):
        """日付の妥当性チェック"""
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', v):
            raise ValueError('日付は YYYY-MM-DD 形式で指定してください')
        return v

class RoutePoint(BaseModel):
    """ルートポイント"""
    longitude: float = Field(..., description="経度")
    latitude: float = Field(..., description="緯度")
    shade_ratio: float = Field(..., ge=0.0, le=1.0, description="日陰率 (0.0-1.0)")
    
    @validator('longitude')
    def validate_longitude(cls, v):
        if not (-180 <= v <= 180):
            raise ValueError('経度は -180 から 180 の範囲で指定してください')
        return v
    
    @validator('latitude')
    def validate_latitude(cls, v):
        if not (-90 <= v <= 90):
            raise ValueError('緯度は -90 から 90 の範囲で指定してください')
        return v

class RouteResponse(BaseModel):
    """ルートレスポンス"""
    route_points: List[RoutePoint] = Field(..., description="ルートポイントのリスト")
    total_distance: float = Field(..., ge=0, description="総距離（メートル）")
    estimated_time: int = Field(..., ge=0, description="推定所要時間（分）")
    average_shade_ratio: float = Field(..., ge=0.0, le=1.0, description="平均日陰率")
    transport_mode: TransportMode = Field(..., description="交通手段")
    area_name: str = Field(..., description="エリア名")
    weather_condition: WeatherCondition = Field(default=WeatherCondition.PARTLY_CLOUDY, description="天気")
    cache_used: bool = Field(default=False, description="キャッシュを使用したか")
    calculation_time_ms: Optional[int] = Field(None, description="計算時間（ミリ秒）")
    
    @validator('route_points')
    def validate_route_points(cls, v):
        if len(v) < 2:
            raise ValueError('ルートポイントは最低2つ必要です')
        return v

class BuildingProperties(BaseModel):
    """建物プロパティ"""
    building: str = Field(default="yes", description="建物タイプ")
    height: float = Field(default=10.0, ge=0, description="建物の高さ（メートル）")
    osm_id: Optional[int] = Field(None, description="OpenStreetMap ID")
    levels: Optional[int] = Field(None, ge=0, description="階数")

class BuildingGeometry(BaseModel):
    """建物ジオメトリ"""
    type: str = Field(..., description="ジオメトリタイプ")
    coordinates: List[List[List[float]]] = Field(..., description="座標リスト")

class Building(BaseModel):
    """建物"""
    type: str = Field(default="Feature", description="フィーチャータイプ")
    geometry: BuildingGeometry = Field(..., description="ジオメトリ")
    properties: BuildingProperties = Field(..., description="プロパティ")

class BuildingCollection(BaseModel):
    """建物コレクション"""
    type: str = Field(default="FeatureCollection", description="コレクションタイプ")
    features: List[Building] = Field(..., description="建物のリスト")

class HealthResponse(BaseModel):
    """ヘルスチェックレスポンス"""
    status: str = Field(..., description="ステータス")
    timestamp: str = Field(..., description="タイムスタンプ")
    version: str = Field(..., description="APIバージョン")
    cache_stats: Optional[Dict[str, Any]] = Field(None, description="キャッシュ統計")

class ErrorResponse(BaseModel):
    """エラーレスポンス"""
    error: str = Field(..., description="エラータイプ")
    message: str = Field(..., description="エラーメッセージ")
    details: Optional[Dict[str, Any]] = Field(None, description="詳細情報")
    timestamp: str = Field(..., description="タイムスタンプ")

class CacheStats(BaseModel):
    """キャッシュ統計"""
    size: int = Field(..., description="現在のキャッシュサイズ")
    max_size: int = Field(..., description="最大キャッシュサイズ")
    hits: int = Field(..., description="ヒット数")
    misses: int = Field(..., description="ミス数")
    hit_rate: float = Field(..., description="ヒット率")
    ttl_seconds: int = Field(..., description="TTL（秒）")

