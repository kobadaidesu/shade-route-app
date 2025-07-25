"""
最小限の動作するAPI
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import datetime
import logging
import math
import requests
import json

logging.basicConfig(level=logging.INFO)

# OSM設定
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
BUILDING_CACHE = {}

app = FastAPI(title="Shade Route API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RouteRequest(BaseModel):
    start: List[float]
    end: List[float]
    time: str
    date: str
    transport_mode: str = "walk"

class RoutePoint(BaseModel):
    longitude: float
    latitude: float
    shade_ratio: float

class RouteResponse(BaseModel):
    route_points: List[RoutePoint]
    total_distance: float
    estimated_time: int
    average_shade_ratio: float
    transport_mode: str
    area_name: str
    weather_condition: str = "partly_cloudy"
    cache_used: bool = False

def get_hal_tokyo_buildings():
    """HAL東京までの範囲の建物データを取得"""
    cache_key = "hal_tokyo_buildings"
    
    if cache_key in BUILDING_CACHE:
        logging.info("Using cached building data for HAL Tokyo area")
        return BUILDING_CACHE[cache_key]
    
    logging.info("Fetching HAL Tokyo area building data from OSM...")
    
    # 新宿駅からHAL東京までの範囲
    bbox = [35.685, 139.695, 35.705, 139.715]  # [south, west, north, east]
    
    overpass_query = f"""
    [out:json][timeout:60];
    (
      way[building]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
      relation[building]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
    );
    out geom;
    """
    
    try:
        response = requests.post(OVERPASS_URL, data=overpass_query, timeout=120)
        response.raise_for_status()
        osm_data = response.json()
        
        buildings = []
        for element in osm_data.get("elements", []):
            if element.get("type") == "way" and "geometry" in element:
                coordinates = [[coord["lon"], coord["lat"]] for coord in element["geometry"]]
                if len(coordinates) > 2:
                    if coordinates[0] != coordinates[-1]:
                        coordinates.append(coordinates[0])
                    
                    # 建物の高さ情報取得
                    tags = element.get("tags", {})
                    try:
                        height = float(str(tags.get("height", "10")).replace("m", ""))
                    except:
                        height = 10
                    try:
                        levels = int(tags.get("building:levels", "3"))
                    except:
                        levels = 3
                    estimated_height = max(height, levels * 3)  # 1階=3m想定
                    
                    buildings.append({
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [coordinates]
                        },
                        "properties": {
                            "building": tags.get("building", "yes"),
                            "height": estimated_height,
                            "osm_id": element.get("id")
                        }
                    })
        
        building_data = {
            "type": "FeatureCollection",
            "features": buildings
        }
        
        BUILDING_CACHE[cache_key] = building_data
        logging.info(f"Retrieved {len(buildings)} buildings for HAL Tokyo area")
        return building_data
        
    except Exception as e:
        logging.error(f"Failed to fetch building data: {e}")
        return {"type": "FeatureCollection", "features": []}

def calculate_building_shadow(lon: float, lat: float, time_str: str, buildings: dict) -> float:
    """建物による日陰を計算"""
    hour = int(time_str.split(":")[0])
    
    # 太陽角度計算（簡易版）
    sun_elevation = 90 - abs(hour - 12) * 7.5  # 正午で90度
    sun_azimuth = (hour - 12) * 15  # 1時間で15度回転
    
    shade_factor = 0.0
    point_x, point_y = lon, lat
    
    for building in buildings.get("features", []):
        try:
            coords = building["geometry"]["coordinates"][0]
            height = building["properties"].get("height", 10)
            
            # 建物の中心座標
            center_x = sum(c[0] for c in coords) / len(coords)
            center_y = sum(c[1] for c in coords) / len(coords)
            
            # 建物からの距離
            distance = ((point_x - center_x) ** 2 + (point_y - center_y) ** 2) ** 0.5
            
            if distance < 0.001:  # 約100m以内
                # 影の長さ計算
                shadow_length = height / math.tan(math.radians(max(sun_elevation, 5)))
                shadow_length_degrees = shadow_length / 111000  # メートルを度に変換
                
                # 影の方向計算
                shadow_direction = math.radians(sun_azimuth + 180)  # 太陽の反対側
                shadow_end_x = center_x + shadow_length_degrees * math.cos(shadow_direction)
                shadow_end_y = center_y + shadow_length_degrees * math.sin(shadow_direction)
                
                # ポイントが影の中にいるかチェック
                shadow_distance = ((point_x - shadow_end_x) ** 2 + (point_y - shadow_end_y) ** 2) ** 0.5
                
                if shadow_distance < shadow_length_degrees * 0.5:  # 影の範囲内
                    building_shade = min(0.8, height / 30.0)  # 高さに応じた日陰率
                    shade_factor = max(shade_factor, building_shade)
                    
        except Exception:
            continue
    
    return min(1.0, shade_factor)

def is_point_inside_building(lon: float, lat: float, buildings: dict) -> bool:
    """指定座標が建物内部にあるかチェック"""
    for building in buildings.get("features", []):
        try:
            coords = building["geometry"]["coordinates"][0]
            
            # Ray casting algorithm (点が多角形内部にあるかチェック)
            x, y = lon, lat
            n = len(coords)
            inside = False
            
            p1x, p1y = coords[0]
            for i in range(1, n + 1):
                p2x, p2y = coords[i % n]
                if y > min(p1y, p2y):
                    if y <= max(p1y, p2y):
                        if x <= max(p1x, p2x):
                            if p1y != p2y:
                                xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                            if p1x == p2x or x <= xinters:
                                inside = not inside
                p1x, p1y = p2x, p2y
                
            if inside:
                return True
                
        except Exception:
            continue
    
    return False

def line_intersects_building(lon1: float, lat1: float, lon2: float, lat2: float, buildings: dict) -> bool:
    """線分が建物と交差するかチェック"""
    # 簡易版: 線分上の複数点をチェック
    steps = 10
    for i in range(steps + 1):
        ratio = i / steps
        check_lon = lon1 + (lon2 - lon1) * ratio
        check_lat = lat1 + (lat2 - lat1) * ratio
        if is_point_inside_building(check_lon, check_lat, buildings):
            return True
    return False

def find_building_avoiding_route(start_lon: float, start_lat: float, 
                                end_lon: float, end_lat: float, 
                                buildings: dict) -> List[tuple]:
    """建物を避けるルートポイントを生成（強化版）"""
    route_points = [(start_lon, start_lat)]
    num_segments = 25  # セグメント数を増加
    
    for i in range(1, num_segments + 1):
        ratio = i / num_segments
        
        # 基本の直線ルート
        target_lon = start_lon + (end_lon - start_lon) * ratio
        target_lat = start_lat + (end_lat - start_lat) * ratio
        
        # 前のポイントから現在のポイントへの線分をチェック
        prev_lon, prev_lat = route_points[-1]
        
        # 線分が建物と交差するかチェック
        if line_intersects_building(prev_lon, prev_lat, target_lon, target_lat, buildings):
            # 建物回避のための迂回ポイントを探す
            detour_distance = 0.0008  # 約80mに拡大
            best_point = None
            min_distance = float('inf')
            
            # 複数の迂回候補を試行
            detour_options = [
                (target_lon, target_lat + detour_distance),  # 北
                (target_lon, target_lat - detour_distance),  # 南
                (target_lon + detour_distance, target_lat),  # 東
                (target_lon - detour_distance, target_lat),  # 西
                (target_lon + detour_distance * 0.7, target_lat + detour_distance * 0.7),  # 北東
                (target_lon - detour_distance * 0.7, target_lat + detour_distance * 0.7),  # 北西
                (target_lon + detour_distance * 0.7, target_lat - detour_distance * 0.7),  # 南東
                (target_lon - detour_distance * 0.7, target_lat - detour_distance * 0.7),  # 南西
            ]
            
            for detour_lon, detour_lat in detour_options:
                # 迂回ポイントが建物内でないかチェック
                if not is_point_inside_building(detour_lon, detour_lat, buildings):
                    # 迂回ポイントへの線分が建物と交差しないかチェック
                    if not line_intersects_building(prev_lon, prev_lat, detour_lon, detour_lat, buildings):
                        # 目標地点に最も近い迂回ポイントを選択
                        distance = ((detour_lon - target_lon) ** 2 + (detour_lat - target_lat) ** 2) ** 0.5
                        if distance < min_distance:
                            min_distance = distance
                            best_point = (detour_lon, detour_lat)
            
            if best_point:
                route_points.append(best_point)
            else:
                # 全ての迂回が失敗した場合、より大きく迂回
                far_detour_lat = target_lat + detour_distance * 2
                route_points.append((target_lon, far_detour_lat))
        else:
            # 建物との交差なし: そのまま追加
            route_points.append((target_lon, target_lat))
    
    # 最終地点を確実に追加
    if route_points[-1] != (end_lon, end_lat):
        route_points.append((end_lon, end_lat))
    
    return route_points

def calculate_shade_ratio(lon: float, lat: float, time_str: str) -> float:
    """実建物データを使った日陰率計算"""
    buildings = get_hal_tokyo_buildings()
    
    # 建物内部の場合は日陰率を0に（建物内は通れない）
    if is_point_inside_building(lon, lat, buildings):
        return 0.0
    
    # 建物による日陰
    building_shade = calculate_building_shadow(lon, lat, time_str, buildings)
    
    # 基本的な時間・位置要因
    hour = int(time_str.split(":")[0])
    base_shade = 0.2 + 0.1 * math.sin((hour - 6) * math.pi / 12)
    position_factor = (lat - 35.695) * 0.5 + (lon - 139.705) * 0.3
    
    # 総合日陰率
    total_shade = building_shade + base_shade + position_factor * 0.05
    return max(0.0, min(1.0, total_shade))

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat()}

@app.get("/api/buildings")
async def get_buildings():
    """建物データを返すAPI"""
    try:
        buildings = get_hal_tokyo_buildings()
        logging.info(f"Returning {len(buildings.get('features', []))} buildings")
        return buildings
    except Exception as e:
        logging.error(f"Failed to get buildings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get buildings: {str(e)}")

@app.post("/api/route/shade-avoid", response_model=RouteResponse)
async def calculate_shade_avoiding_route(request: RouteRequest):
    try:
        start_lon, start_lat = request.start
        end_lon, end_lat = request.end
        
        # 建物回避ルート生成
        buildings = get_hal_tokyo_buildings()
        avoiding_route = find_building_avoiding_route(start_lon, start_lat, end_lon, end_lat, buildings)
        
        route_points = []
        for lon, lat in avoiding_route:
            shade_ratio = calculate_shade_ratio(lon, lat, request.time)
            route_points.append(RoutePoint(
                longitude=lon,
                latitude=lat,
                shade_ratio=shade_ratio
            ))
        
        # 距離計算
        total_distance = 0
        for i in range(len(route_points) - 1):
            p1, p2 = route_points[i], route_points[i + 1]
            dist = ((p2.longitude - p1.longitude) ** 2 + (p2.latitude - p1.latitude) ** 2) ** 0.5 * 111000
            total_distance += dist
        
        # 平均日陰率
        avg_shade = sum(p.shade_ratio for p in route_points) / len(route_points)
        
        # 所要時間計算
        speed_map = {"walk": 5, "bike": 15, "car": 30}  # km/h
        speed = speed_map.get(request.transport_mode, 5)
        estimated_time = max(1, int((total_distance / 1000) / speed * 60))
        
        return RouteResponse(
            route_points=route_points,
            total_distance=total_distance,
            estimated_time=estimated_time,
            average_shade_ratio=avg_shade,
            transport_mode=request.transport_mode,
            area_name="新宿区〜HAL東京",
            weather_condition="partly_cloudy",
            cache_used=len(BUILDING_CACHE) > 0
        )
        
    except Exception as e:
        logging.error(f"Route calculation error: {e}")
        raise HTTPException(status_code=500, detail=f"Route calculation failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)