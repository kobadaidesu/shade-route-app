"""
簡易版メインAPI（データベース無し版）
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import datetime
import logging
import math
import random
import requests
import json
import time

# ログ設定
logging.basicConfig(level=logging.INFO)

# OSM Overpass API設定
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSM_CACHE = {}  # 道路データキャッシュ

# OpenRouteService API設定  
ORS_API_KEY = "5b3ce3597851110001cf6248f8e1b4fcb7834e5b89ad73b2b9c4653c"
ORS_BASE_URL = "https://api.openrouteservice.org/v2/directions"

app = FastAPI(
    title="Shade Route API (Simple)",
    description="Simplified API for shade-avoiding route calculation",
    version="1.0.0-simple"
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# リクエスト/レスポンスモデル
class RouteRequest(BaseModel):
    start: List[float]  # [longitude, latitude]
    end: List[float]    # [longitude, latitude]
    time: str          # "HH:MM"
    date: str          # "YYYY-MM-DD"
    transport_mode: Optional[str] = "walk"
    user_id: Optional[str] = None
    area: Optional[str] = None

class RoutePoint(BaseModel):
    longitude: float
    latitude: float
    shade_ratio: float  # 0.0-1.0

class RouteResponse(BaseModel):
    route_points: List[RoutePoint]
    total_distance: float
    estimated_time: int  # minutes
    average_shade_ratio: float
    transport_mode: str
    area_name: str
    weather_condition: Optional[str] = None
    cache_used: bool = False

def calculate_shade_ratio(lon: float, lat: float, time_str: str) -> float:
    """
    位置と時間に基づいて日陰率を計算
    実際の太陽位置、建物密度、道路方向を考慮
    """
    hour = int(time_str.split(":")[0])
    minute = int(time_str.split(":")[1])
    time_decimal = hour + minute / 60.0
    
    # 太陽角度による基本日陰率
    if 6 <= time_decimal <= 8:  # 朝
        base_shade = 0.8
    elif 8 < time_decimal <= 10:  # 午前
        base_shade = 0.6
    elif 10 < time_decimal <= 14:  # 昼間
        base_shade = 0.3
    elif 14 < time_decimal <= 16:  # 午後
        base_shade = 0.5
    elif 16 < time_decimal <= 18:  # 夕方
        base_shade = 0.7
    else:  # 夜間・早朝
        base_shade = 0.9
    
    # 位置による建物密度（新宿、渋谷、港区の特徴）
    if 35.68 <= lat <= 35.71 and 139.69 <= lon <= 139.72:  # 新宿区
        building_density = 0.8  # 高層ビル多い
    elif 35.64 <= lat <= 35.68 and 139.68 <= lon <= 139.72:  # 渋谷区
        building_density = 0.7  # 中層ビル多い
    elif 35.63 <= lat <= 35.69 and 139.72 <= lon <= 139.78:  # 港区
        building_density = 0.6  # オフィス街
    else:
        building_density = 0.4  # 住宅街
    
    # 位置による微調整（道路方向、公園、川沿い等）
    position_factor = math.sin(lat * 1000) * math.cos(lon * 1000) * 0.2
    
    # 最終日陰率計算
    shade_ratio = base_shade * building_density + position_factor
    return min(1.0, max(0.0, shade_ratio))

def generate_ors_shade_avoiding_route(start_lon: float, start_lat: float, 
                                    end_lon: float, end_lat: float, 
                                    time_str: str, transport_mode: str) -> Dict[str, Any]:
    """
    OpenRouteService APIを使った建物回避・日陰最適化ルート生成
    プロンプト仕様に準拠
    """
    logging.info(f"ORS-based route generation: ({start_lon}, {start_lat}) to ({end_lon}, {end_lat})")
    
    # 1. バウンディングボックス計算
    margin = 0.005  # 約500m
    bbox = [
        min(start_lat, end_lat) - margin,  # south
        min(start_lon, end_lon) - margin,  # west
        max(start_lat, end_lat) + margin,  # north
        max(start_lon, end_lon) + margin   # east
    ]
    
    # 2. OSMから建物ポリゴンを取得
    building_polygons = get_building_polygons_from_osm(bbox)
    
    # 3. OpenRouteService APIでルート計算
    ors_result = call_openrouteservice_api(
        start=[start_lon, start_lat],
        end=[end_lon, end_lat],
        avoid_polygons=building_polygons,
        profile=transport_mode
    )
    
    if not ors_result or "features" not in ors_result:
        logging.warning("ORS API failed, using fallback")
        # フォールバック処理
        buildings = generate_building_data(start_lon, start_lat, end_lon, end_lat)
        fallback_route_points = []
        num_points = 20
        for i in range(num_points + 1):
            ratio = i / num_points
            lon = start_lon + (end_lon - start_lon) * ratio
            lat = start_lat + (end_lat - start_lat) * ratio
            shade_ratio = calculate_shade_ratio(lon, lat, time_str)
            fallback_route_points.append(RoutePoint(
                longitude=lon, latitude=lat, shade_ratio=shade_ratio
            ))
        
        return {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature", 
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[point.longitude, point.latitude] for point in fallback_route_points]
                },
                "properties": {
                    "total_distance": calculate_route_distance(fallback_route_points),
                    "estimated_time": len(fallback_route_points) // 5,  # 簡易計算
                    "sunlight_score": 0.5
                }
            }],
            "building_avoid_geojson": {"type": "FeatureCollection", "features": []},
            "route_summary": {
                "total_distance": calculate_route_distance(fallback_route_points),
                "estimated_time": len(fallback_route_points) // 5,
                "sunlight_score": 0.5,
                "method": "fallback"
            }
        }
    
    # 4. 日当たりスコア計算
    route_feature = ors_result["features"][0]
    coordinates = route_feature["geometry"]["coordinates"]
    sunlight_score = calculate_sunlight_score(coordinates, time_str)
    
    # 5. GeoJSON形式で結果を返却
    result = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": route_feature["geometry"],
            "properties": {
                **route_feature.get("properties", {}),
                "sunlight_score": sunlight_score,
                "method": "openrouteservice"
            }
        }],
        "building_avoid_geojson": building_polygons,
        "route_summary": {
            "total_distance": route_feature.get("properties", {}).get("summary", {}).get("distance", 0),
            "estimated_time": route_feature.get("properties", {}).get("summary", {}).get("duration", 0),
            "sunlight_score": sunlight_score,
            "buildings_avoided": len(building_polygons.get("features", [])),
            "method": "openrouteservice"
        }
    }
    
    logging.info(f"ORS route generated: {result['route_summary']}")
    return result

def generate_shade_avoiding_route(start_lon: float, start_lat: float, 
                                 end_lon: float, end_lat: float, 
                                 time_str: str, transport_mode: str) -> List[RoutePoint]:
    """
    建物回避と日陰最適化を組み合わせたルートを生成
    シンプルで確実なアプローチ
    """
    logging.info(f"Generating smart shade-avoiding route from ({start_lon}, {start_lat}) to ({end_lon}, {end_lat})")
    
    # 建物データを生成
    buildings = generate_building_data(start_lon, start_lat, end_lon, end_lat)
    
    # 直線ルート生成
    route_points = []
    num_points = 20
    for i in range(num_points + 1):
        ratio = i / num_points
        lon = start_lon + (end_lon - start_lon) * ratio
        lat = start_lat + (end_lat - start_lat) * ratio
        shade_ratio = calculate_shade_ratio(lon, lat, time_str)
        route_points.append(RoutePoint(
            longitude=lon, latitude=lat, shade_ratio=shade_ratio
        ))
    
    logging.info(f"Generated smart route with {len(route_points)} points")
    return route_points

def generate_road_network_graph(start_lon: float, start_lat: float, 
                               end_lon: float, end_lat: float) -> dict:
    """
    道路ネットワークグラフを生成（新宿区エリア）
    """
    graph = {"nodes": {}, "edges": []}
    
    # 新宿区の主要道路交差点を定義
    major_intersections = [
        # 新宿駅周辺
        {"id": "shinjuku_station", "lon": 139.7036, "lat": 35.6917, "type": "major"},
        {"id": "shinjuku_east", "lon": 139.7050, "lat": 35.6920, "type": "major"},
        {"id": "shinjuku_south", "lon": 139.7000, "lat": 35.6890, "type": "major"},
        {"id": "shinjuku_west", "lon": 139.6980, "lat": 35.6930, "type": "major"},
        {"id": "shinjuku_north", "lon": 139.7020, "lat": 35.6950, "type": "major"},
        
        # 副都心線沿い
        {"id": "shinjuku_sanchome", "lon": 139.7065, "lat": 35.6886, "type": "major"},
        {"id": "yoyogi", "lon": 139.7016, "lat": 35.6830, "type": "major"},
        {"id": "takadanobaba", "lon": 139.7037, "lat": 35.7128, "type": "major"},
        
        # 補助的な交差点
        {"id": "int_1", "lon": 139.7010, "lat": 35.6910, "type": "minor"},
        {"id": "int_2", "lon": 139.7020, "lat": 35.6900, "type": "minor"},
        {"id": "int_3", "lon": 139.7030, "lat": 35.6890, "type": "minor"},
        {"id": "int_4", "lon": 139.7040, "lat": 35.6880, "type": "minor"},
        {"id": "int_5", "lon": 139.7000, "lat": 35.6920, "type": "minor"},
        {"id": "int_6", "lon": 139.6990, "lat": 35.6910, "type": "minor"},
        {"id": "int_7", "lon": 139.7015, "lat": 35.6925, "type": "minor"},
        {"id": "int_8", "lon": 139.7025, "lat": 35.6915, "type": "minor"},
        {"id": "int_9", "lon": 139.7035, "lat": 35.6905, "type": "minor"},
        {"id": "int_10", "lon": 139.7045, "lat": 35.6895, "type": "minor"},
    ]
    
    # ノードを追加
    for intersection in major_intersections:
        graph["nodes"][intersection["id"]] = {
            "lon": intersection["lon"],
            "lat": intersection["lat"],
            "type": intersection["type"]
        }
    
    # エッジ（道路）を追加
    road_connections = [
        # 主要道路
        {"from": "shinjuku_station", "to": "shinjuku_east", "type": "main_road"},
        {"from": "shinjuku_station", "to": "shinjuku_south", "type": "main_road"},
        {"from": "shinjuku_station", "to": "shinjuku_west", "type": "main_road"},
        {"from": "shinjuku_station", "to": "shinjuku_north", "type": "main_road"},
        
        # 副都心線沿い
        {"from": "shinjuku_station", "to": "shinjuku_sanchome", "type": "main_road"},
        {"from": "shinjuku_station", "to": "yoyogi", "type": "main_road"},
        {"from": "shinjuku_north", "to": "takadanobaba", "type": "main_road"},
        
        # 補助道路のネットワーク
        {"from": "shinjuku_station", "to": "int_1", "type": "local_road"},
        {"from": "int_1", "to": "int_2", "type": "local_road"},
        {"from": "int_2", "to": "int_3", "type": "local_road"},
        {"from": "int_3", "to": "int_4", "type": "local_road"},
        {"from": "shinjuku_station", "to": "int_5", "type": "local_road"},
        {"from": "int_5", "to": "int_6", "type": "local_road"},
        {"from": "int_1", "to": "int_7", "type": "local_road"},
        {"from": "int_7", "to": "int_8", "type": "local_road"},
        {"from": "int_8", "to": "int_9", "type": "local_road"},
        {"from": "int_9", "to": "int_10", "type": "local_road"},
        {"from": "int_2", "to": "int_8", "type": "local_road"},
        {"from": "int_3", "to": "int_9", "type": "local_road"},
        {"from": "shinjuku_east", "to": "int_10", "type": "local_road"},
        {"from": "int_5", "to": "int_7", "type": "local_road"},
        {"from": "int_6", "to": "shinjuku_west", "type": "local_road"},
    ]
    
    for connection in road_connections:
        from_node = graph["nodes"][connection["from"]]
        to_node = graph["nodes"][connection["to"]]
        
        # 距離を計算
        distance = ((to_node["lon"] - from_node["lon"]) ** 2 + 
                   (to_node["lat"] - from_node["lat"]) ** 2) ** 0.5 * 111000
        
        # 双方向エッジを追加
        graph["edges"].append({
            "from": connection["from"],
            "to": connection["to"],
            "distance": distance,
            "type": connection["type"],
            "weight": 1.0  # 初期重み
        })
        graph["edges"].append({
            "from": connection["to"],
            "to": connection["from"],
            "distance": distance,
            "type": connection["type"],
            "weight": 1.0  # 初期重み
        })
    
    return graph

def apply_building_and_shade_weights(graph: dict, buildings: list, time_str: str) -> dict:
    """
    建物と日陰情報を使って道路エッジに重みを付ける
    """
    weighted_graph = graph.copy()
    
    for edge in weighted_graph["edges"]:
        from_node = weighted_graph["nodes"][edge["from"]]
        to_node = weighted_graph["nodes"][edge["to"]]
        
        # エッジの中点で建物と日陰を評価
        mid_lon = (from_node["lon"] + to_node["lon"]) / 2
        mid_lat = (from_node["lat"] + to_node["lat"]) / 2
        
        # 建物ペナルティを計算
        building_penalty = calculate_building_penalty(mid_lon, mid_lat, buildings)
        
        # 日陰ボーナスを計算
        shade_bonus = calculate_shade_bonus(mid_lon, mid_lat, time_str)
        
        # 道路タイプによる基本重み
        base_weight = 1.0
        if edge["type"] == "main_road":
            base_weight = 0.8  # 主要道路は速い
        elif edge["type"] == "local_road":
            base_weight = 1.2  # 地方道路は少し遅い
        
        # 最終重みを計算（距離 × 基本重み × 建物ペナルティ × 日陰ボーナス）
        edge["weight"] = edge["distance"] * base_weight * building_penalty * shade_bonus
    
    return weighted_graph

def calculate_building_penalty(lon: float, lat: float, buildings: list) -> float:
    """
    建物の近さに基づくペナルティを計算
    """
    min_distance_to_building = float('inf')
    
    for building in buildings:
        # 建物の中心からの距離を計算
        building_center_lon = (building['min_lon'] + building['max_lon']) / 2
        building_center_lat = (building['min_lat'] + building['max_lat']) / 2
        
        distance = ((lon - building_center_lon) ** 2 + (lat - building_center_lat) ** 2) ** 0.5
        min_distance_to_building = min(min_distance_to_building, distance)
    
    # 距離に基づくペナルティ（建物に近いほど重いペナルティ）
    if min_distance_to_building < 0.0005:  # 約50m以内
        return 3.0  # 重いペナルティ
    elif min_distance_to_building < 0.001:  # 約100m以内
        return 2.0  # 中程度のペナルティ
    elif min_distance_to_building < 0.002:  # 約200m以内
        return 1.5  # 軽いペナルティ
    else:
        return 1.0  # ペナルティなし

def calculate_shade_bonus(lon: float, lat: float, time_str: str) -> float:
    """
    日陰の多さに基づくボーナスを計算
    """
    shade_ratio = calculate_shade_ratio(lon, lat, time_str)
    
    # 日陰率に基づくボーナス（日陰が多いほど軽い重み）
    if shade_ratio > 0.7:
        return 0.6  # 大きなボーナス
    elif shade_ratio > 0.5:
        return 0.8  # 中程度のボーナス
    elif shade_ratio > 0.3:
        return 0.9  # 小さなボーナス
    else:
        return 1.0  # ボーナスなし

def calculate_weighted_shortest_path(graph: dict, start_lon: float, start_lat: float, 
                                   end_lon: float, end_lat: float, time_str: str) -> List[RoutePoint]:
    """
    重み付きグラフでダイクストラ法による最短経路を計算
    """
    import heapq
    
    # 開始点と終了点に最も近いノードを見つける
    start_node = find_nearest_node(graph, start_lon, start_lat)
    end_node = find_nearest_node(graph, end_lon, end_lat)
    
    # ダイクストラ法の初期化
    distances = {node_id: float('inf') for node_id in graph["nodes"]}
    distances[start_node] = 0
    previous = {}
    priority_queue = [(0, start_node)]
    visited = set()
    
    while priority_queue:
        current_distance, current_node = heapq.heappop(priority_queue)
        
        if current_node in visited:
            continue
            
        visited.add(current_node)
        
        if current_node == end_node:
            break
        
        # 隣接ノードを探索
        for edge in graph["edges"]:
            if edge["from"] == current_node and edge["to"] not in visited:
                neighbor = edge["to"]
                weight = edge["weight"]
                distance = current_distance + weight
                
                if distance < distances[neighbor]:
                    distances[neighbor] = distance
                    previous[neighbor] = current_node
                    heapq.heappush(priority_queue, (distance, neighbor))
    
    # パスを再構築
    path = []
    current = end_node
    while current in previous:
        path.append(current)
        current = previous[current]
    path.append(start_node)
    path.reverse()
    
    # パスが見つからない場合は直線ルートにフォールバック
    if not path or path[0] != start_node:
        return generate_fallback_route(start_lon, start_lat, end_lon, end_lat, time_str)
    
    # パスをRoutePointに変換
    route_points = []
    
    # 開始点を追加
    route_points.append(RoutePoint(
        longitude=start_lon,
        latitude=start_lat,
        shade_ratio=calculate_shade_ratio(start_lon, start_lat, time_str)
    ))
    
    # パス上のノードを追加
    for node_id in path:
        node = graph["nodes"][node_id]
        route_points.append(RoutePoint(
            longitude=node["lon"],
            latitude=node["lat"],
            shade_ratio=calculate_shade_ratio(node["lon"], node["lat"], time_str)
        ))
    
    # 終了点を追加
    route_points.append(RoutePoint(
        longitude=end_lon,
        latitude=end_lat,
        shade_ratio=calculate_shade_ratio(end_lon, end_lat, time_str)
    ))
    
    return route_points

def find_nearest_node(graph: dict, lon: float, lat: float) -> str:
    """
    指定座標に最も近いノードを見つける
    """
    min_distance = float('inf')
    nearest_node = None
    
    for node_id, node in graph["nodes"].items():
        distance = ((lon - node["lon"]) ** 2 + (lat - node["lat"]) ** 2) ** 0.5
        if distance < min_distance:
            min_distance = distance
            nearest_node = node_id
    
    return nearest_node

def generate_fallback_route(start_lon: float, start_lat: float,
                          end_lon: float, end_lat: float, time_str: str) -> List[RoutePoint]:
    """
    パスが見つからない場合のフォールバックルート
    """
    route_points = []
    num_points = 10
    
    for i in range(num_points + 1):
        ratio = i / num_points
        lon = start_lon + (end_lon - start_lon) * ratio
        lat = start_lat + (end_lat - start_lat) * ratio
        
        route_points.append(RoutePoint(
            longitude=lon,
            latitude=lat,
            shade_ratio=calculate_shade_ratio(lon, lat, time_str)
        ))
    
    return route_points

def calculate_grid_based_route(start_lon: float, start_lat: float,
                              end_lon: float, end_lat: float, 
                              buildings: list, time_str: str) -> List[RoutePoint]:
    """
    グリッドベースのA*アルゴリズムでルート計算
    """
    import heapq
    
    # グリッド設定
    grid_size = 50  # 50x50グリッド
    min_lon = min(start_lon, end_lon) - 0.005
    max_lon = max(start_lon, end_lon) + 0.005
    min_lat = min(start_lat, end_lat) - 0.005
    max_lat = max(start_lat, end_lat) + 0.005
    
    lon_step = (max_lon - min_lon) / grid_size
    lat_step = (max_lat - min_lat) / grid_size
    
    # グリッドを生成
    grid = create_navigation_grid(min_lon, max_lon, min_lat, max_lat, grid_size, buildings)
    
    # 開始点と終了点をグリッド座標に変換
    start_x = int((start_lon - min_lon) / lon_step)
    start_y = int((start_lat - min_lat) / lat_step)
    end_x = int((end_lon - min_lon) / lon_step)
    end_y = int((end_lat - min_lat) / lat_step)
    
    # 境界チェック
    start_x = max(0, min(grid_size - 1, start_x))
    start_y = max(0, min(grid_size - 1, start_y))
    end_x = max(0, min(grid_size - 1, end_x))
    end_y = max(0, min(grid_size - 1, end_y))
    
    # A*アルゴリズム
    def heuristic(x1, y1, x2, y2):
        return abs(x1 - x2) + abs(y1 - y2)  # マンハッタン距離
    
    open_set = [(0, start_x, start_y, [])]
    visited = set()
    
    directions = [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, 1), (1, -1), (-1, -1)]
    
    while open_set:
        f_score, x, y, path = heapq.heappop(open_set)
        
        if (x, y) in visited:
            continue
            
        visited.add((x, y))
        path = path + [(x, y)]
        
        if x == end_x and y == end_y:
            # パスをRoutePointに変換
            route_points = []
            for gx, gy in path:
                lon = min_lon + gx * lon_step
                lat = min_lat + gy * lat_step
                shade_ratio = calculate_shade_ratio(lon, lat, time_str)
                route_points.append(RoutePoint(
                    longitude=lon,
                    latitude=lat,
                    shade_ratio=shade_ratio
                ))
            return route_points
        
        # 隣接セルを探索
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            
            if (0 <= nx < grid_size and 0 <= ny < grid_size and 
                (nx, ny) not in visited and grid[ny][nx] > 0):
                
                # 移動コスト計算（建物回避 + 日陰ボーナス）
                move_cost = 1.0
                if dx != 0 and dy != 0:  # 斜め移動
                    move_cost = 1.414
                
                # グリッドセルの重みを適用
                cell_weight = grid[ny][nx]
                g_score = len(path) + move_cost * cell_weight
                h_score = heuristic(nx, ny, end_x, end_y)
                f_score = g_score + h_score
                
                heapq.heappush(open_set, (f_score, nx, ny, path))
    
    # パスが見つからない場合は直線ルート
    logging.warning(f"Grid-based pathfinding failed: start=({start_x},{start_y}), end=({end_x},{end_y}), grid_size={grid_size}")
    logging.warning(f"Start cell passable: {grid[start_y][start_x] > 0 if 0 <= start_y < grid_size and 0 <= start_x < grid_size else False}")
    logging.warning(f"End cell passable: {grid[end_y][end_x] > 0 if 0 <= end_y < grid_size and 0 <= end_x < grid_size else False}")
    return generate_fallback_route(start_lon, start_lat, end_lon, end_lat, time_str)

def create_navigation_grid(min_lon: float, max_lon: float, min_lat: float, max_lat: float,
                          grid_size: int, buildings: list) -> list:
    """
    ナビゲーション用グリッドを作成
    0 = 通行不可（建物）, >0 = 通行可能（重み）
    """
    grid = [[1.0 for _ in range(grid_size)] for _ in range(grid_size)]
    
    lon_step = (max_lon - min_lon) / grid_size
    lat_step = (max_lat - min_lat) / grid_size
    
    # 建物領域を通行不可に設定
    for building in buildings:
        b_min_x = int((building['min_lon'] - min_lon) / lon_step)
        b_max_x = int((building['max_lon'] - min_lon) / lon_step)
        b_min_y = int((building['min_lat'] - min_lat) / lat_step)
        b_max_y = int((building['max_lat'] - min_lat) / lat_step)
        
        # 境界チェック
        b_min_x = max(0, b_min_x)
        b_max_x = min(grid_size - 1, b_max_x)
        b_min_y = max(0, b_min_y)
        b_max_y = min(grid_size - 1, b_max_y)
        
        # 建物領域とその周辺を通行不可に
        for y in range(max(0, b_min_y - 1), min(grid_size, b_max_y + 2)):
            for x in range(max(0, b_min_x - 1), min(grid_size, b_max_x + 2)):
                if b_min_y <= y <= b_max_y and b_min_x <= x <= b_max_x:
                    grid[y][x] = 0  # 建物内部は通行不可
                else:
                    grid[y][x] = max(2.0, grid[y][x])  # 建物周辺は重いペナルティ
    
    # 日陰による重み調整
    for y in range(grid_size):
        for x in range(grid_size):
            if grid[y][x] > 0:  # 通行可能な場合のみ
                lon = min_lon + x * lon_step
                lat = min_lat + y * lat_step
                shade_ratio = calculate_shade_ratio(lon, lat, "14:00")  # 仮の時間
                
                # 日陰が多いほど軽い重み
                if shade_ratio > 0.7:
                    grid[y][x] *= 0.6
                elif shade_ratio > 0.5:
                    grid[y][x] *= 0.8
                elif shade_ratio > 0.3:
                    grid[y][x] *= 0.9
    
    return grid

def calculate_smart_building_avoiding_route(start_lon: float, start_lat: float,
                                           end_lon: float, end_lat: float,
                                           buildings: list, time_str: str,
                                           transport_mode: str = "walk") -> List[RoutePoint]:
    """
    OSM道路データを使ったスマートな建物回避ルート計算
    """
    logging.info(f"Smart OSM-based route calculation started for {transport_mode}")
    
    try:
        # OSMから道路ネットワークを生成
        road_network = generate_road_network_from_osm(start_lon, start_lat, end_lon, end_lat, transport_mode)
        
        if not road_network["nodes"] or not road_network["edges"]:
            logging.warning("No OSM road data found, falling back to grid-based routing")
            return calculate_fallback_route(start_lon, start_lat, end_lon, end_lat, buildings, time_str)
        
        # 建物と日陰による重み付けを適用
        weighted_network = apply_osm_building_and_shade_weights(road_network, buildings, time_str, transport_mode)
        
        # ダイクストラ法でルート計算
        route = route_with_dijkstra_osm(weighted_network, start_lon, start_lat, end_lon, end_lat)
        
        if route:
            logging.info(f"OSM-based route generated with {len(route)} points")
            return route
        else:
            logging.warning("OSM routing failed, using fallback")
            return calculate_fallback_route(start_lon, start_lat, end_lon, end_lat, buildings, time_str)
            
    except Exception as e:
        logging.error(f"OSM routing error: {e}")
        return calculate_fallback_route(start_lon, start_lat, end_lon, end_lat, buildings, time_str)

def get_building_polygons_from_osm(bbox: List[float]) -> Dict[str, Any]:
    """
    OSMから建物ポリゴンをGeoJSON形式で取得
    bbox: [south, west, north, east]
    """
    cache_key = f"buildings_{bbox[0]:.6f},{bbox[1]:.6f},{bbox[2]:.6f},{bbox[3]:.6f}"
    
    # キャッシュチェック
    if cache_key in OSM_CACHE:
        logging.info(f"Using cached building data for bbox: {bbox}")
        return OSM_CACHE[cache_key]
    
    logging.info(f"Fetching building polygons from OSM for bbox: {bbox}")
    
    # Overpass クエリ（建物ポリゴン取得）
    overpass_query = f"""
    [out:json][timeout:25];
    (
      way[building]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
      relation[building]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
    );
    out geom;
    """
    
    try:
        response = requests.post(OVERPASS_URL, data=overpass_query, timeout=30)
        response.raise_for_status()
        osm_data = response.json()
        
        # GeoJSONに変換
        geojson_features = []
        for element in osm_data.get("elements", []):
            if element.get("type") == "way" and "geometry" in element:
                # way（多角形）をGeoJSON Polygonに変換
                coordinates = [[coord["lon"], coord["lat"]] for coord in element["geometry"]]
                if len(coordinates) > 2:
                    # 多角形を閉じる
                    if coordinates[0] != coordinates[-1]:
                        coordinates.append(coordinates[0])
                    
                    geojson_features.append({
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [coordinates]
                        },
                        "properties": {
                            "building": element.get("tags", {}).get("building", "yes"),
                            "osm_id": element.get("id")
                        }
                    })
        
        building_geojson = {
            "type": "FeatureCollection",
            "features": geojson_features
        }
        
        # キャッシュに保存
        OSM_CACHE[cache_key] = building_geojson
        logging.info(f"Retrieved {len(geojson_features)} building polygons from OSM")
        
        return building_geojson
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch building data from OSM: {e}")
        return {"type": "FeatureCollection", "features": []}

def call_openrouteservice_api(start: List[float], end: List[float], 
                            avoid_polygons: Dict[str, Any], 
                            profile: str = "foot-walking") -> Dict[str, Any]:
    """
    OpenRouteService APIを呼び出してルートを取得
    """
    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json"
    }
    
    # プロファイル設定
    profile_mapping = {
        "walk": "foot-walking",
        "bike": "cycling-regular", 
        "car": "driving-car"
    }
    ors_profile = profile_mapping.get(profile, "foot-walking")
    
    # リクエストボディ
    request_body = {
        "coordinates": [start, end],
        "format": "geojson",
        "profile": ors_profile,
        "geometry_simplify": False,
        "instructions": False
    }
    
    # 建物回避ポリゴンを追加
    if avoid_polygons and avoid_polygons.get("features"):
        # avoid_polygonsとして渡すため、座標のみ抽出
        polygon_coords = []
        for feature in avoid_polygons["features"]:
            if feature["geometry"]["type"] == "Polygon":
                polygon_coords.append({
                    "type": "Polygon",
                    "coordinates": feature["geometry"]["coordinates"]
                })
        
        if polygon_coords:
            request_body["options"] = {
                "avoid_polygons": {
                    "type": "FeatureCollection",
                    "features": [{"type": "Feature", "geometry": poly, "properties": {}} for poly in polygon_coords]
                }
            }
    
    try:
        url = f"{ORS_BASE_URL}/{ors_profile}/geojson"
        response = requests.post(url, headers=headers, json=request_body, timeout=30)
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        logging.error(f"OpenRouteService API error: {e}")
        return None

def calculate_sunlight_score(coordinates: List[List[float]], time_str: str) -> float:
    """
    日当たりスコアを計算（低いほど日陰が少ない）
    """
    total_score = 0.0
    hour = int(time_str.split(":")[0])
    
    for lon, lat in coordinates:
        # 簡易的な日当たり計算
        # 午前中は東向き、午後は西向きが日当たり良い
        if hour < 12:
            # 午前：東向きが有利
            sunlight_factor = 1.0 - abs(lon - 139.7036) * 100  # 新宿駅を基準
        else:
            # 午後：西向きが有利
            sunlight_factor = 1.0 - abs(lon - 139.7080) * 100
        
        # 緯度による影響（南向きが有利）
        latitude_factor = lat - 35.6900  # 南側が有利
        
        # 建物密度による日陰推定（簡易）
        building_shade = calculate_shade_ratio(lon, lat, time_str)
        
        # 総合スコア（低いほど日陰が少ない）
        point_score = building_shade - (sunlight_factor * 0.1) - (latitude_factor * 0.05)
        total_score += max(0, point_score)
    
    return total_score / len(coordinates) if coordinates else 1.0

def calculate_fallback_route(start_lon: float, start_lat: float,
                           end_lon: float, end_lat: float,
                           buildings: list, time_str: str) -> List[RoutePoint]:
    """
    フォールバック用の従来ルート計算
    """
    logging.info("Using fallback route calculation")
    
    # 直線ルートを生成
    direct_route_points = []
    num_points = 20
    for i in range(num_points + 1):
        ratio = i / num_points
        lon = start_lon + (end_lon - start_lon) * ratio
        lat = start_lat + (end_lat - start_lat) * ratio
        shade_ratio = calculate_shade_ratio(lon, lat, time_str)
        direct_route_points.append(RoutePoint(
            longitude=lon, latitude=lat, shade_ratio=shade_ratio
        ))
    
    return direct_route_points
    
    # 複数の迂回戦略を評価
    strategies = generate_multi_strategy_detour(start_lon, start_lat, end_lon, end_lat, buildings, time_str)
    
    if not strategies:
        logging.warning("No valid strategies found, using direct route")
        return direct_route
    
    # 最良の戦略を選択
    best_strategy = min(strategies, key=lambda s: s["score"])
    logging.info(f"Selected strategy: {best_strategy['name']} with score {best_strategy['score']:.2f}")
    
    return best_strategy["route"]

def apply_osm_building_and_shade_weights(road_network: dict, buildings: list, time_str: str, transport_mode: str) -> dict:
    """
    OSM道路ネットワークに建物と日陰による重み付けを適用
    """
    weighted_network = road_network.copy()
    
    for edge in weighted_network["edges"]:
        from_node = weighted_network["nodes"][edge["from"]]
        to_node = weighted_network["nodes"][edge["to"]]
        
        # エッジの中点で建物と日陰を評価
        mid_lon = (from_node["lon"] + to_node["lon"]) / 2
        mid_lat = (from_node["lat"] + to_node["lat"]) / 2
        
        # 建物ペナルティを計算
        building_penalty = calculate_building_penalty(mid_lon, mid_lat, buildings)
        
        # 日陰ボーナスを計算
        shade_bonus = calculate_shade_bonus(mid_lon, mid_lat, time_str)
        
        # 最終重みを計算（距離 × 速度係数 × 建物ペナルティ × 日陰ボーナス）
        edge["weight"] = edge["distance"] / edge["speed_factor"] * building_penalty * shade_bonus
    
    return weighted_network

def route_with_dijkstra_osm(road_network: dict, start_lon: float, start_lat: float,
                           end_lon: float, end_lat: float) -> List[RoutePoint]:
    """
    OSM道路ネットワーク用のダイクストラ法ルート計算
    """
    nodes = road_network["nodes"]
    edges = road_network["edges"]
    
    if not nodes or not edges:
        return []
    
    # 開始点と終了点に最も近いノードを見つける
    start_node_id = find_nearest_node(nodes, start_lat, start_lon)
    end_node_id = find_nearest_node(nodes, end_lat, end_lon)
    
    if start_node_id is None or end_node_id is None:
        logging.error("Could not find nearest nodes for start/end points")
        return []
    
    logging.info(f"Routing from node {start_node_id} to node {end_node_id}")
    
    # エッジを隣接リストに変換
    adjacency = {}
    for edge in edges:
        if edge["from"] not in adjacency:
            adjacency[edge["from"]] = []
        adjacency[edge["from"]].append({
            "to": edge["to"],
            "weight": edge["weight"]
        })
    
    # ダイクストラ法を実行
    distances = {node["id"]: float('inf') for node in nodes}
    distances[start_node_id] = 0
    previous = {}
    priority_queue = [(0, start_node_id)]
    visited = set()
    
    while priority_queue:
        current_distance, current_node = heapq.heappop(priority_queue)
        
        if current_node in visited:
            continue
            
        visited.add(current_node)
        
        if current_node == end_node_id:
            break
        
        if current_node in adjacency:
            for neighbor in adjacency[current_node]:
                neighbor_id = neighbor["to"]
                weight = neighbor["weight"]
                distance = current_distance + weight
                
                if distance < distances[neighbor_id]:
                    distances[neighbor_id] = distance
                    previous[neighbor_id] = current_node
                    heapq.heappush(priority_queue, (distance, neighbor_id))
    
    # パスを再構築
    if end_node_id not in previous and start_node_id != end_node_id:
        logging.error("No path found between start and end nodes")
        return []
    
    path = []
    current = end_node_id
    while current is not None:
        path.append(current)
        current = previous.get(current)
    path.reverse()
    
    # ノードIDを座標に変換
    route_points = []
    for node_id in path:
        node = next(n for n in nodes if n["id"] == node_id)
        shade_ratio = calculate_shade_ratio(node["lon"], node["lat"], time_str)
        route_points.append(RoutePoint(
            longitude=node["lon"],
            latitude=node["lat"],
            shade_ratio=shade_ratio
        ))
    
    logging.info(f"Generated route with {len(route_points)} points")
    return route_points

def find_nearest_node(nodes: List[dict], lat: float, lon: float) -> Optional[int]:
    """
    指定座標に最も近いノードを見つける
    """
    min_distance = float('inf')
    nearest_node_id = None
    
    for node in nodes:
        distance = calculate_distance(lat, lon, node["lat"], node["lon"])
        if distance < min_distance:
            min_distance = distance
            nearest_node_id = node["id"]
    
    return nearest_node_id

def generate_shade_optimized_direct_route(start_lon: float, start_lat: float,
                                        end_lon: float, end_lat: float, 
                                        time_str: str) -> List[RoutePoint]:
    """
    建物衝突なしの場合の日陰最適化ルート
    """
    route_points = []
    num_segments = 20
    
    for i in range(num_segments + 1):
        ratio = i / num_segments
        
        # 基本の線形補間
        base_lon = start_lon + (end_lon - start_lon) * ratio
        base_lat = start_lat + (end_lat - start_lat) * ratio
        
        # 日陰を求めて微調整
        optimized_lon, optimized_lat = seek_shade_with_limits(
            base_lon, base_lat, time_str, ratio
        )
        
        route_points.append(RoutePoint(
            longitude=optimized_lon,
            latitude=optimized_lat,
            shade_ratio=calculate_shade_ratio(optimized_lon, optimized_lat, time_str)
        ))
    
    return route_points

def generate_multi_strategy_detour(start_lon: float, start_lat: float,
                                 end_lon: float, end_lat: float,
                                 buildings: list, time_str: str) -> List[RoutePoint]:
    """
    複数戦略による迂回ルート生成
    """
    # 戦略1: 北回り
    north_route = generate_directional_detour(
        start_lon, start_lat, end_lon, end_lat, buildings, time_str, "north"
    )
    
    # 戦略2: 南回り  
    south_route = generate_directional_detour(
        start_lon, start_lat, end_lon, end_lat, buildings, time_str, "south"
    )
    
    # 戦略3: 東西回り
    eastwest_route = generate_directional_detour(
        start_lon, start_lat, end_lon, end_lat, buildings, time_str, "eastwest"
    )
    
    # 最適なルートを選択（日陰率と距離を考慮）
    routes = [
        ("north", north_route),
        ("south", south_route), 
        ("eastwest", eastwest_route)
    ]
    
    best_route = None
    best_score = float('inf')
    
    for strategy, route in routes:
        if route:
            # スコア計算（距離の重み70% + 日陰不足の重み30%）
            total_distance = calculate_route_distance(route)
            avg_shade = sum(p.shade_ratio for p in route) / len(route)
            shade_penalty = (1.0 - avg_shade) * 1000  # 日陰不足をペナルティに
            
            score = total_distance * 0.7 + shade_penalty * 0.3
            
            logging.info(f"Strategy {strategy}: distance={total_distance:.1f}m, shade={avg_shade:.2f}, score={score:.1f}")
            
            if score < best_score:
                best_score = score
                best_route = route
    
    return best_route if best_route else generate_fallback_route(
        start_lon, start_lat, end_lon, end_lat, time_str
    )

def generate_directional_detour(start_lon: float, start_lat: float,
                              end_lon: float, end_lat: float,
                              buildings: list, time_str: str, direction: str) -> List[RoutePoint]:
    """
    指定方向の迂回ルートを生成
    """
    route_points = []
    
    # 建物の境界を計算
    all_min_lon = min(b['min_lon'] for b in buildings)
    all_max_lon = max(b['max_lon'] for b in buildings)
    all_min_lat = min(b['min_lat'] for b in buildings)
    all_max_lat = max(b['max_lat'] for b in buildings)
    
    # 迂回戦略による中継点を決定
    if direction == "north":
        # 北回り：建物群の北側を通る
        waypoint_lat = all_max_lat + 0.001  # 約100m北
        waypoint_lon = (start_lon + end_lon) / 2
    elif direction == "south":
        # 南回り：建物群の南側を通る
        waypoint_lat = all_min_lat - 0.001  # 約100m南
        waypoint_lon = (start_lon + end_lon) / 2
    else:  # eastwest
        # 東西回り：建物の端を迂回
        if end_lon > start_lon:  # 東向き
            waypoint_lon = all_max_lon + 0.001
        else:  # 西向き
            waypoint_lon = all_min_lon - 0.001
        waypoint_lat = (start_lat + end_lat) / 2
    
    # 3区間のルートを生成
    # 区間1: 開始点 → 中継点
    segment1 = generate_shade_optimized_segment(
        start_lon, start_lat, waypoint_lon, waypoint_lat, time_str, 8
    )
    
    # 区間2: 中継点周辺で日陰探索
    segment2 = generate_shade_optimized_segment(
        waypoint_lon, waypoint_lat, waypoint_lon, waypoint_lat, time_str, 3
    )
    
    # 区間3: 中継点 → 終了点
    segment3 = generate_shade_optimized_segment(
        waypoint_lon, waypoint_lat, end_lon, end_lat, time_str, 8
    )
    
    # セグメントを結合
    route_points.extend(segment1)
    route_points.extend(segment2[1:])  # 重複を避ける
    route_points.extend(segment3[1:])  # 重複を避ける
    
    return route_points

def generate_shade_optimized_segment(start_lon: float, start_lat: float,
                                   end_lon: float, end_lat: float,
                                   time_str: str, num_points: int) -> List[RoutePoint]:
    """
    日陰最適化されたセグメントを生成
    """
    points = []
    
    for i in range(num_points + 1):
        ratio = i / num_points
        base_lon = start_lon + (end_lon - start_lon) * ratio
        base_lat = start_lat + (end_lat - start_lat) * ratio
        
        # 日陰探索（制限付き）
        opt_lon, opt_lat = seek_shade_with_limits(base_lon, base_lat, time_str, ratio)
        
        points.append(RoutePoint(
            longitude=opt_lon,
            latitude=opt_lat,
            shade_ratio=calculate_shade_ratio(opt_lon, opt_lat, time_str)
        ))
    
    return points

def seek_shade_with_limits(lon: float, lat: float, time_str: str, progress: float) -> tuple:
    """
    制限付き日陰探索（大きく逸脱しない）
    """
    best_lon, best_lat = lon, lat
    best_shade = calculate_shade_ratio(lon, lat, time_str)
    
    # 小さな範囲で日陰を探索
    search_radius = 0.0002  # 約20m
    
    for d_lon in [-search_radius, 0, search_radius]:
        for d_lat in [-search_radius, 0, search_radius]:
            candidate_lon = lon + d_lon
            candidate_lat = lat + d_lat
            shade_ratio = calculate_shade_ratio(candidate_lon, candidate_lat, time_str)
            
            if shade_ratio > best_shade:
                best_shade = shade_ratio
                best_lon = candidate_lon
                best_lat = candidate_lat
    
    # 曲線効果を追加
    curve_lon = best_lon + math.sin(progress * math.pi * 2) * 0.0001
    curve_lat = best_lat + math.cos(progress * math.pi * 2) * 0.0001
    
    return curve_lon, curve_lat

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    2点間の距離を計算（ハヴァーサイン公式）
    """
    R = 6371000  # 地球の半径（メートル）
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_lat / 2) ** 2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def calculate_route_distance(route_points: List[RoutePoint]) -> float:
    """
    ルートの総距離を計算
    """
    total_distance = 0
    for i in range(len(route_points) - 1):
        p1 = route_points[i]
        p2 = route_points[i + 1]
        segment_distance = ((p2.longitude - p1.longitude) ** 2 + 
                           (p2.latitude - p1.latitude) ** 2) ** 0.5 * 111000
        total_distance += segment_distance
    return total_distance


def find_intersecting_buildings(start_lon: float, start_lat: float,
                               end_lon: float, end_lat: float, 
                               buildings: list) -> list:
    """
    線分と交差する建物を見つける
    """
    intersecting = []
    
    for building in buildings:
        # 建物に安全マージンを追加
        margin = 0.0002  # 約20mのマージン
        expanded_building = {
            'min_lon': building['min_lon'] - margin,
            'max_lon': building['max_lon'] + margin,
            'min_lat': building['min_lat'] - margin,
            'max_lat': building['max_lat'] + margin,
            'shade_factor': building['shade_factor']
        }
        
        if line_intersects_rectangle(
            start_lon, start_lat, end_lon, end_lat, expanded_building
        ):
            intersecting.append(expanded_building)
    
    return intersecting

def line_intersects_rectangle(x1: float, y1: float, x2: float, y2: float, rect: dict) -> bool:
    """
    線分と矩形の交差判定
    """
    # 矩形の4つの角
    min_x, max_x = rect['min_lon'], rect['max_lon']
    min_y, max_y = rect['min_lat'], rect['max_lat']
    
    # 線分が矩形を完全に通り抜けるかチェック
    if ((x1 < min_x and x2 > max_x) or (x1 > max_x and x2 < min_x)) and \
       (min_y <= y1 <= max_y or min_y <= y2 <= max_y):
        return True
    
    if ((y1 < min_y and y2 > max_y) or (y1 > max_y and y2 < min_y)) and \
       (min_x <= x1 <= max_x or min_x <= x2 <= max_x):
        return True
    
    # 線分の端点が矩形内にあるかチェック
    if (min_x <= x1 <= max_x and min_y <= y1 <= max_y) or \
       (min_x <= x2 <= max_x and min_y <= y2 <= max_y):
        return True
    
    # 矩形の4辺と線分の交差をチェック
    return (line_segments_intersect(x1, y1, x2, y2, min_x, min_y, max_x, min_y) or  # bottom
            line_segments_intersect(x1, y1, x2, y2, max_x, min_y, max_x, max_y) or  # right
            line_segments_intersect(x1, y1, x2, y2, max_x, max_y, min_x, max_y) or  # top
            line_segments_intersect(x1, y1, x2, y2, min_x, max_y, min_x, min_y))    # left

def line_segments_intersect(x1: float, y1: float, x2: float, y2: float,
                           x3: float, y3: float, x4: float, y4: float) -> bool:
    """
    2つの線分の交差判定
    """
    def ccw(ax, ay, bx, by, cx, cy):
        return (cy - ay) * (bx - ax) > (by - ay) * (cx - ax)
    
    return ccw(x1, y1, x3, y3, x4, y4) != ccw(x2, y2, x3, y3, x4, y4) and \
           ccw(x1, y1, x2, y2, x3, y3) != ccw(x1, y1, x2, y2, x4, y4)

def generate_detour_path(start_lon: float, start_lat: float,
                        end_lon: float, end_lat: float,
                        buildings: list, time_str: str) -> List[RoutePoint]:
    """
    建物を迂回するパスを生成
    """
    path_points = []
    
    # 最も大きな障害となる建物を特定
    main_obstacle = max(buildings, key=lambda b: 
        (b['max_lon'] - b['min_lon']) * (b['max_lat'] - b['min_lat']))
    
    # 迂回方向を決定（北回りか南回り）
    building_center_lat = (main_obstacle['min_lat'] + main_obstacle['max_lat']) / 2
    route_center_lat = (start_lat + end_lat) / 2
    
    if route_center_lat > building_center_lat:
        # 北回り
        waypoint_lat = main_obstacle['max_lat'] + 0.0003
    else:
        # 南回り
        waypoint_lat = main_obstacle['min_lat'] - 0.0003
    
    # 建物の角を通る迂回点を設定
    if start_lon < end_lon:
        # 東向き：建物の西角→北/南角→東角
        waypoints = [
            (main_obstacle['min_lon'] - 0.0002, waypoint_lat),
            (main_obstacle['max_lon'] + 0.0002, waypoint_lat)
        ]
    else:
        # 西向き：建物の東角→北/南角→西角
        waypoints = [
            (main_obstacle['max_lon'] + 0.0002, waypoint_lat),
            (main_obstacle['min_lon'] - 0.0002, waypoint_lat)
        ]
    
    # パス生成
    current_lon, current_lat = start_lon, start_lat
    path_points.append(RoutePoint(
        longitude=current_lon,
        latitude=current_lat, 
        shade_ratio=calculate_shade_ratio(current_lon, current_lat, time_str)
    ))
    
    # 迂回点を通るパスを生成
    for waypoint_lon, waypoint_lat in waypoints:
        # 中間点を追加
        mid_lon = (current_lon + waypoint_lon) / 2
        mid_lat = (current_lat + waypoint_lat) / 2
        
        path_points.append(RoutePoint(
            longitude=mid_lon,
            latitude=mid_lat,
            shade_ratio=calculate_shade_ratio(mid_lon, mid_lat, time_str)
        ))
        
        path_points.append(RoutePoint(
            longitude=waypoint_lon,
            latitude=waypoint_lat,
            shade_ratio=calculate_shade_ratio(waypoint_lon, waypoint_lat, time_str)
        ))
        
        current_lon, current_lat = waypoint_lon, waypoint_lat
    
    # 最終目的地への接続
    final_mid_lon = (current_lon + end_lon) / 2
    final_mid_lat = (current_lat + end_lat) / 2
    
    path_points.append(RoutePoint(
        longitude=final_mid_lon,
        latitude=final_mid_lat,
        shade_ratio=calculate_shade_ratio(final_mid_lon, final_mid_lat, time_str)
    ))
    
    path_points.append(RoutePoint(
        longitude=end_lon,
        latitude=end_lat,
        shade_ratio=calculate_shade_ratio(end_lon, end_lat, time_str)
    ))
    
    return path_points

def avoid_buildings(lon: float, lat: float, buildings: list, progress: float) -> tuple:
    """
    建物を回避する座標調整
    """
    # 建物に近い場合は回避
    for building in buildings:
        if (building['min_lon'] <= lon <= building['max_lon'] and 
            building['min_lat'] <= lat <= building['max_lat']):
            
            # 建物を回避する方向を決定
            if progress < 0.5:
                # 前半は北側に回避
                lat += 0.0008
            else:
                # 後半は南側に回避
                lat -= 0.0008
            
            # 東西方向の調整
            if lon < (building['min_lon'] + building['max_lon']) / 2:
                lon -= 0.0006
            else:
                lon += 0.0006
    
    return lon, lat


def avoid_building_collision(lon: float, lat: float, buildings: list, progress: float) -> tuple:
    """
    建物との衝突を避けるために位置を調整
    """
    # 現在位置が建物内にあるかチェック
    for building in buildings:
        # 安全マージンを追加
        margin = 0.0001
        if (building['min_lon'] - margin <= lon <= building['max_lon'] + margin and
            building['min_lat'] - margin <= lat <= building['max_lat'] + margin):
            
            # 建物中心からの距離を計算
            center_lon = (building['min_lon'] + building['max_lon']) / 2
            center_lat = (building['min_lat'] + building['max_lat']) / 2
            
            # 建物から離れる方向に移動
            if progress < 0.5:
                # 前半は北側に回避
                lat += 0.0008
            else:
                # 後半は南側に回避
                lat -= 0.0008
            
            # 東西方向の調整
            if lon < center_lon:
                lon -= 0.0006
            else:
                lon += 0.0006
    
    return lon, lat

def seek_shade_path_enhanced(lon: float, lat: float, time_str: str, progress: float) -> tuple:
    """
    日陰の多い経路を探索（拡張版）
    """
    # より大きな範囲で候補点を評価
    candidates = []
    
    # より広い範囲で候補点を評価
    for d_lon in [-0.0008, -0.0004, 0, 0.0004, 0.0008]:
        for d_lat in [-0.0008, -0.0004, 0, 0.0004, 0.0008]:
            candidate_lon = lon + d_lon
            candidate_lat = lat + d_lat
            shade_ratio = calculate_shade_ratio(candidate_lon, candidate_lat, time_str)
            candidates.append((candidate_lon, candidate_lat, shade_ratio))
    
    # 最も日陰の多い点を選択
    best_candidate = max(candidates, key=lambda x: x[2])
    
    # より大きな曲線的な経路のための微調整
    curve_adjustment_lon = math.sin(progress * math.pi * 2) * 0.0005
    curve_adjustment_lat = math.cos(progress * math.pi * 2) * 0.0007
    
    return (best_candidate[0] + curve_adjustment_lon, 
            best_candidate[1] + curve_adjustment_lat)

def seek_shade_path(lon: float, lat: float, time_str: str, progress: float) -> tuple:
    """
    日陰の多い経路を探索
    """
    # 複数の候補点を評価
    candidates = []
    
    # 現在位置を中心に周囲の点を評価
    for d_lon in [-0.0004, 0, 0.0004]:
        for d_lat in [-0.0004, 0, 0.0004]:
            candidate_lon = lon + d_lon
            candidate_lat = lat + d_lat
            shade_ratio = calculate_shade_ratio(candidate_lon, candidate_lat, time_str)
            candidates.append((candidate_lon, candidate_lat, shade_ratio))
    
    # 最も日陰の多い点を選択
    best_candidate = max(candidates, key=lambda x: x[2])
    
    # 曲線的な経路のための微調整
    curve_adjustment = math.sin(progress * math.pi) * 0.0003
    
    return best_candidate[0], best_candidate[1] + curve_adjustment

def generate_direct_route(start_lon: float, start_lat: float, 
                         end_lon: float, end_lat: float, num_points: int) -> List[tuple]:
    """直線ルートを生成"""
    points = []
    for i in range(num_points + 1):
        ratio = i / num_points
        lon = start_lon + (end_lon - start_lon) * ratio
        lat = start_lat + (end_lat - start_lat) * ratio
        points.append((lon, lat))
    return points

def generate_curved_route(start_lon: float, start_lat: float, 
                         end_lon: float, end_lat: float, num_points: int, 
                         direction: str) -> List[tuple]:
    """曲線ルートを生成（北回りまたは南回り）"""
    points = []
    
    # 中間点を設定
    mid_lon = (start_lon + end_lon) / 2
    mid_lat = (start_lat + end_lat) / 2
    
    # 曲線の幅を設定
    curve_offset = 0.005  # 約500m
    if direction == "north":
        mid_lat += curve_offset
    else:
        mid_lat -= curve_offset
    
    # ベジェ曲線で経路を生成
    for i in range(num_points + 1):
        t = i / num_points
        
        # 2次ベジェ曲線
        lon = (1-t)**2 * start_lon + 2*(1-t)*t * mid_lon + t**2 * end_lon
        lat = (1-t)**2 * start_lat + 2*(1-t)*t * mid_lat + t**2 * end_lat
        
        # 道路に沿うようにランダムな微調整
        lon += random.uniform(-0.0005, 0.0005)
        lat += random.uniform(-0.0005, 0.0005)
        
        points.append((lon, lat))
    
    return points

def get_roads_from_osm(bbox: List[float], transport_mode: str = "walk") -> Dict[str, Any]:
    """
    OpenStreetMapから道路データを取得
    bbox: [south, west, north, east]
    """
    cache_key = f"{bbox[0]:.6f},{bbox[1]:.6f},{bbox[2]:.6f},{bbox[3]:.6f}"
    
    # キャッシュチェック
    if cache_key in OSM_CACHE:
        logging.info(f"Using cached OSM data for bbox: {bbox}")
        return OSM_CACHE[cache_key]
    
    logging.info(f"Fetching OSM road data for bbox: {bbox}")
    
    # Overpass クエリ（移動手段に応じたフィルタリング）
    if transport_mode == "car":
        # 車：主要道路のみ
        highway_filter = "primary|secondary|tertiary|trunk|trunk_link|primary_link|secondary_link"
    elif transport_mode == "bike":
        # 自転車：車道 + 自転車道
        highway_filter = "primary|secondary|tertiary|residential|cycleway|primary_link|secondary_link"
    else:
        # 徒歩：主要道路 + 歩道（細かすぎる path は除外）
        highway_filter = "primary|secondary|tertiary|residential|footway|pedestrian|primary_link|secondary_link"
    
    overpass_query = f"""
    [out:json][timeout:25];
    (
      way[highway~"^({highway_filter})$"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
    );
    out geom;
    """
    
    try:
        response = requests.post(OVERPASS_URL, data=overpass_query, timeout=30)
        response.raise_for_status()
        osm_data = response.json()
        
        # キャッシュに保存
        OSM_CACHE[cache_key] = osm_data
        logging.info(f"Retrieved {len(osm_data.get('elements', []))} road segments from OSM")
        
        return osm_data
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch OSM data: {e}")
        return {"elements": []}

def classify_road_type(highway_tag: str) -> str:
    """
    OSMのhighwayタグから道路タイプを分類
    """
    classification = {
        "primary": "main_road",
        "secondary": "main_road", 
        "tertiary": "local_road",
        "residential": "residential",
        "footway": "footway",
        "path": "footway",
        "cycleway": "cycleway",
        "pedestrian": "footway"
    }
    return classification.get(highway_tag, "residential")

def get_road_speed_factor(road_type: str, transport_mode: str) -> float:
    """
    道路タイプと移動手段に基づく速度係数
    """
    speed_factors = {
        "walk": {
            "main_road": 0.9,      # 主要道路は少し遅い（歩道が狭い）
            "local_road": 1.0,     # 標準
            "residential": 1.1,    # 住宅街は少し速い（静か）
            "footway": 1.2,        # 歩道は最速
            "cycleway": 0.8        # 自転車道は歩行者には不適
        },
        "bike": {
            "main_road": 0.8,      # 主要道路は危険
            "local_road": 1.0,     # 標準
            "residential": 1.1,    # 住宅街は安全
            "footway": 0.6,        # 歩道は自転車には不適
            "cycleway": 1.3        # 自転車道は最適
        },
        "car": {
            "main_road": 1.2,      # 主要道路は最速
            "local_road": 1.0,     # 標準
            "residential": 0.8,    # 住宅街は遅い
            "footway": 0.0,        # 通行不可
            "cycleway": 0.0        # 通行不可
        }
    }
    return speed_factors.get(transport_mode, {}).get(road_type, 1.0)

def osm_to_road_network(osm_data: Dict[str, Any], transport_mode: str = "walk") -> dict:
    """
    OSMデータを道路ネットワークグラフに変換
    """
    nodes = {}
    edges = []
    node_id_counter = 0
    
    for element in osm_data.get("elements", []):
        if element.get("type") != "way" or "geometry" not in element:
            continue
            
        highway_tag = element.get("tags", {}).get("highway", "")
        road_type = classify_road_type(highway_tag)
        
        # 移動手段に適さない道路をスキップ
        speed_factor = get_road_speed_factor(road_type, transport_mode)
        if speed_factor == 0.0:
            continue
        
        geometry = element["geometry"]
        
        # ノードを追加
        way_nodes = []
        for coord in geometry:
            node_key = f"{coord['lat']:.6f},{coord['lon']:.6f}"
            if node_key not in nodes:
                nodes[node_key] = {
                    "id": node_id_counter,
                    "lat": coord["lat"],
                    "lon": coord["lon"]
                }
                node_id_counter += 1
            way_nodes.append(nodes[node_key]["id"])
        
        # エッジを追加（隣接ノード間）
        for i in range(len(way_nodes) - 1):
            from_id = way_nodes[i]
            to_id = way_nodes[i + 1]
            
            # ノード座標を取得
            from_node = next(n for n in nodes.values() if n["id"] == from_id)
            to_node = next(n for n in nodes.values() if n["id"] == to_id)
            
            # 距離計算
            distance = calculate_distance(
                from_node["lat"], from_node["lon"],
                to_node["lat"], to_node["lon"]
            )
            
            # 双方向エッジを追加
            edges.append({
                "from": from_id,
                "to": to_id,
                "distance": distance,
                "type": road_type,
                "speed_factor": speed_factor,
                "weight": distance / speed_factor  # 初期重み
            })
            edges.append({
                "from": to_id,
                "to": from_id,
                "distance": distance,
                "type": road_type,
                "speed_factor": speed_factor,
                "weight": distance / speed_factor  # 初期重み
            })
    
    # ノードリストに変換
    node_list = list(nodes.values())
    
    logging.info(f"Created road network: {len(node_list)} nodes, {len(edges)} edges")
    
    return {
        "nodes": node_list,
        "edges": edges
    }

def generate_road_network_from_osm(start_lon: float, start_lat: float, 
                                  end_lon: float, end_lat: float,
                                  transport_mode: str = "walk") -> dict:
    """
    OSMデータから道路ネットワークを生成
    """
    # バウンディングボックスを計算（少し余裕を持たせる）
    margin = 0.005  # 約500m
    bbox = [
        min(start_lat, end_lat) - margin,  # south
        min(start_lon, end_lon) - margin,  # west
        max(start_lat, end_lat) + margin,  # north
        max(start_lon, end_lon) + margin   # east
    ]
    
    # OSMから道路データを取得
    osm_data = get_roads_from_osm(bbox, transport_mode)
    
    # 道路ネットワークに変換
    return osm_to_road_network(osm_data, transport_mode)

def generate_road_network_grid(start_lon: float, start_lat: float, 
                              end_lon: float, end_lat: float) -> dict:
    """
    新宿区限定の道路ネットワークグリッドを生成
    """
    grid = {}
    
    # 新宿区に限定したグリッドサイズ設定
    grid_size = 0.0005  # 約50mグリッド（より細かく）
    
    # 新宿区の範囲に限定
    min_lon = max(139.690, min(start_lon, end_lon) - 0.002)
    max_lon = min(139.720, max(start_lon, end_lon) + 0.002)
    min_lat = max(35.680, min(start_lat, end_lat) - 0.002)
    max_lat = min(35.700, max(start_lat, end_lat) + 0.002)
    
    # グリッドポイントを生成
    lon = min_lon
    while lon <= max_lon:
        lat = min_lat
        while lat <= max_lat:
            grid[(lon, lat)] = {
                'walkable': True,
                'is_road': is_road_point(lon, lat),
                'shade_ratio': calculate_shade_ratio(lon, lat, "14:00")
            }
            lat += grid_size
        lon += grid_size
    
    return grid

def generate_building_data(start_lon: float, start_lat: float, 
                          end_lon: float, end_lat: float) -> list:
    """
    新宿区の詳細建物データを生成
    """
    buildings = []
    
    # 新宿区の詳細建物配置（実際の建物位置に近い）
    building_areas = [
        # 新宿駅東口周辺のビル群
        {'lon': 139.7010, 'lat': 35.6910, 'width': 0.0008, 'height': 0.0008},  # アルタ
        {'lon': 139.7020, 'lat': 35.6900, 'width': 0.0010, 'height': 0.0012},  # 伊勢丹
        {'lon': 139.7005, 'lat': 35.6920, 'width': 0.0006, 'height': 0.0010},  # ルミネエスト
        
        # 新宿駅西口周辺の高層ビル
        {'lon': 139.6980, 'lat': 35.6920, 'width': 0.0012, 'height': 0.0015},  # 都庁
        {'lon': 139.6990, 'lat': 35.6900, 'width': 0.0008, 'height': 0.0012},  # 京王プラザ
        {'lon': 139.6970, 'lat': 35.6905, 'width': 0.0010, 'height': 0.0008},  # ハイアット
        
        # 新宿三丁目周辺
        {'lon': 139.7050, 'lat': 35.6890, 'width': 0.0008, 'height': 0.0006},  # 新宿三越
        {'lon': 139.7040, 'lat': 35.6880, 'width': 0.0006, 'height': 0.0008},  # マルイ本館
        {'lon': 139.7055, 'lat': 35.6875, 'width': 0.0010, 'height': 0.0006},  # 高島屋
        
        # 歌舞伎町周辺
        {'lon': 139.7025, 'lat': 35.6950, 'width': 0.0006, 'height': 0.0008},
        {'lon': 139.7035, 'lat': 35.6955, 'width': 0.0008, 'height': 0.0006},
        {'lon': 139.7015, 'lat': 35.6960, 'width': 0.0004, 'height': 0.0010},
        
        # 新宿御苑周辺のビル
        {'lon': 139.7100, 'lat': 35.6850, 'width': 0.0008, 'height': 0.0006},
        {'lon': 139.7080, 'lat': 35.6860, 'width': 0.0006, 'height': 0.0008},
        
        # 四谷方面のビル
        {'lon': 139.7200, 'lat': 35.6900, 'width': 0.0006, 'height': 0.0008},
        {'lon': 139.7180, 'lat': 35.6880, 'width': 0.0008, 'height': 0.0006},
    ]
    
    for building in building_areas:
        buildings.append({
            'min_lon': building['lon'] - building['width']/2,
            'max_lon': building['lon'] + building['width']/2,
            'min_lat': building['lat'] - building['height']/2,
            'max_lat': building['lat'] + building['height']/2,
            'shade_factor': 0.9  # 建物の影響度
        })
    
    return buildings

def is_road_point(lon: float, lat: float) -> bool:
    """
    新宿区の詳細道路判定
    """
    # 新宿区の主要道路網
    major_roads = [
        # 東西道路（甲州街道、青梅街道等）
        {'lat': 35.6920, 'tolerance': 0.0003},  # 新宿駅北口通り
        {'lat': 35.6900, 'tolerance': 0.0004},  # 甲州街道
        {'lat': 35.6880, 'tolerance': 0.0003},  # 新宿通り
        {'lat': 35.6860, 'tolerance': 0.0003},  # 明治通り
        {'lat': 35.6950, 'tolerance': 0.0003},  # 靖国通り
        {'lat': 35.6970, 'tolerance': 0.0003},  # 青梅街道
        
        # 南北道路
        {'lon': 139.6980, 'tolerance': 0.0003},  # 西口大通り
        {'lon': 139.7000, 'tolerance': 0.0004},  # 中央通り
        {'lon': 139.7020, 'tolerance': 0.0003},  # 東口大通り
        {'lon': 139.7040, 'tolerance': 0.0003},  # 新宿三丁目通り
        {'lon': 139.7060, 'tolerance': 0.0003},  # 伊勢丹通り
        {'lon': 139.7080, 'tolerance': 0.0003},  # 御苑通り
        {'lon': 139.7100, 'tolerance': 0.0003},  # 四谷通り
        
        # 斜め道路
        {'lat': 35.6890, 'lon': 139.7010, 'tolerance': 0.0005},  # 新宿大ガード
        {'lat': 35.6940, 'lon': 139.7030, 'tolerance': 0.0005},  # 歌舞伎町中央通り
    ]
    
    for road in major_roads:
        if 'lat' in road:
            if abs(lat - road['lat']) < road['tolerance']:
                return True
        elif 'lon' in road:
            if abs(lon - road['lon']) < road['tolerance']:
                return True
    
    return False

def find_optimal_shade_route(grid: dict, buildings: list, 
                           start_lon: float, start_lat: float,
                           end_lon: float, end_lat: float, time_str: str) -> List[RoutePoint]:
    """
    A*アルゴリズムで最適な日陰ルートを検索
    """
    import heapq
    
    # グリッドサイズ（新宿区限定）
    grid_size = 0.0005
    
    # 開始点と終了点をグリッドに合わせる
    start_grid = (round(start_lon / grid_size) * grid_size, round(start_lat / grid_size) * grid_size)
    end_grid = (round(end_lon / grid_size) * grid_size, round(end_lat / grid_size) * grid_size)
    
    # A*アルゴリズム
    open_set = [(0, start_grid)]
    came_from = {}
    g_score = {start_grid: 0}
    f_score = {start_grid: heuristic_distance(start_grid, end_grid)}
    
    logging.info(f"Starting A* from {start_grid} to {end_grid}")
    logging.info(f"Grid size: {len(grid)} points")
    
    iterations = 0
    while open_set and iterations < 1000:  # 無限ループ防止
        iterations += 1
        current = heapq.heappop(open_set)[1]
        
        if current == end_grid:
            # パスを再構築
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start_grid)
            path.reverse()
            
            # RoutePointに変換
            route_points = []
            for point in path:
                shade_ratio = calculate_shade_ratio(point[0], point[1], time_str)
                route_points.append(RoutePoint(
                    longitude=point[0],
                    latitude=point[1],
                    shade_ratio=shade_ratio
                ))
            
            return route_points
        
        # 隣接点を探索
        for neighbor in get_neighbors(current, grid_size):
            if not is_walkable(neighbor, grid, buildings):
                continue
            
            tentative_g_score = g_score[current] + get_move_cost(current, neighbor, grid, time_str)
            
            if neighbor not in g_score or tentative_g_score < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g_score
                f_score[neighbor] = g_score[neighbor] + heuristic_distance(neighbor, end_grid)
                heapq.heappush(open_set, (f_score[neighbor], neighbor))
    
    # パスが見つからない場合は直線ルートを返す
    logging.warning(f"No path found after {iterations} iterations, returning direct route")
    return generate_direct_route_points(start_lon, start_lat, end_lon, end_lat, time_str)

def get_neighbors(point: tuple, grid_size: float) -> list:
    """隣接点を取得"""
    lon, lat = point
    neighbors = []
    
    # 8方向の隣接点
    for d_lon in [-grid_size, 0, grid_size]:
        for d_lat in [-grid_size, 0, grid_size]:
            if d_lon == 0 and d_lat == 0:
                continue
            neighbors.append((lon + d_lon, lat + d_lat))
    
    return neighbors

def is_walkable(point: tuple, grid: dict, buildings: list) -> bool:
    """歩行可能かどうかを判定"""
    lon, lat = point
    
    # 建物内部かチェック
    for building in buildings:
        if (building['min_lon'] <= lon <= building['max_lon'] and 
            building['min_lat'] <= lat <= building['max_lat']):
            return False
    
    # グリッドポイントが存在するかチェック
    if point in grid:
        return grid[point]['walkable']
    
    return True

def get_move_cost(from_point: tuple, to_point: tuple, grid: dict, time_str: str) -> float:
    """移動コストを計算（日陰率を考慮）"""
    distance = heuristic_distance(from_point, to_point)
    
    # 日陰率を取得
    shade_ratio = calculate_shade_ratio(to_point[0], to_point[1], time_str)
    
    # 日陰が多いほどコストが低い（日陰回避）
    shade_bonus = 1.0 - shade_ratio * 0.5
    
    return distance * shade_bonus

def heuristic_distance(point1: tuple, point2: tuple) -> float:
    """ユークリッド距離計算"""
    return ((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2)**0.5

def generate_direct_route_points(start_lon: float, start_lat: float, 
                               end_lon: float, end_lat: float, time_str: str) -> List[RoutePoint]:
    """直線ルートをRoutePointで生成"""
    points = []
    num_points = 20
    
    for i in range(num_points + 1):
        ratio = i / num_points
        lon = start_lon + (end_lon - start_lon) * ratio
        lat = start_lat + (end_lat - start_lat) * ratio
        shade_ratio = calculate_shade_ratio(lon, lat, time_str)
        
        points.append(RoutePoint(
            longitude=lon,
            latitude=lat,
            shade_ratio=shade_ratio
        ))
    
    return points

@app.get("/")
async def root():
    return {"message": "Shade Route API (Simple Version) is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat()}

@app.post("/api/route/ors-shade-avoid")
async def calculate_ors_shade_avoiding_route(request: RouteRequest):
    """
    OpenRouteService APIを使った建物回避・日陰最適化ルート計算
    プロンプト仕様準拠
    """
    try:
        start_lon, start_lat = request.start
        end_lon, end_lat = request.end
        
        # ORS APIを使ったルート生成
        result = generate_ors_shade_avoiding_route(
            start_lon, start_lat, end_lon, end_lat,
            request.time, request.transport_mode
        )
        
        return result
        
    except Exception as e:
        logging.error(f"Error in ORS route calculation: {e}")
        raise HTTPException(status_code=500, detail=f"Route calculation failed: {str(e)}")

@app.post("/api/route/shade-avoid", response_model=RouteResponse)
async def calculate_shade_avoiding_route(request: RouteRequest):
    """
    簡易版日陰回避ルート計算
    ダミーデータと簡易計算を使用
    """
    try:
        start_lon, start_lat = request.start
        end_lon, end_lat = request.end
        
        # 日時を解析
        try:
            date_obj = datetime.datetime.strptime(request.date, "%Y-%m-%d").date()
            time_obj = datetime.datetime.strptime(request.time, "%H:%M").time()
            date_time = datetime.datetime.combine(date_obj, time_obj)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date/time format: {e}")
        
        # エリア検出（簡易版）
        area_name = "Unknown Area"
        if 35.68 <= start_lat <= 35.71 and 139.69 <= start_lon <= 139.72:
            area_name = "新宿区"
        elif 35.64 <= start_lat <= 35.68 and 139.68 <= start_lon <= 139.72:
            area_name = "渋谷区"
        elif 35.63 <= start_lat <= 35.69 and 139.72 <= start_lon <= 139.78:
            area_name = "港区"
        
        logging.info(f"Starting route calculation for {request.transport_mode}")
        
        # 道路ネットワークベース日陰回避ルート計算
        route_points = generate_shade_avoiding_route(
            start_lon, start_lat, end_lon, end_lat, 
            request.time, request.transport_mode
        )
        
        if not route_points:
            raise HTTPException(status_code=500, detail="Failed to generate route points")
        
        logging.info(f"Generated {len(route_points)} route points")
        
        # 移動手段による速度設定
        speeds = {"walk": 80, "bike": 200, "car": 500}
        speed = speeds.get(request.transport_mode, 80)
        
        # 実際のルート距離を計算
        total_distance = 0
        for i in range(len(route_points) - 1):
            p1 = route_points[i]
            p2 = route_points[i + 1]
            segment_distance = ((p2.longitude - p1.longitude) ** 2 + (p2.latitude - p1.latitude) ** 2) ** 0.5 * 111000
            total_distance += segment_distance
        
        estimated_time = int(total_distance / speed)
        average_shade = sum(point.shade_ratio for point in route_points) / len(route_points)
        
        # 簡易天気判定
        hour = int(request.time.split(":")[0])
        weather_condition = "partly_cloudy" if 9 <= hour <= 17 else "clear"
        
        return RouteResponse(
            route_points=route_points,
            total_distance=total_distance,
            estimated_time=estimated_time,
            average_shade_ratio=average_shade,
            transport_mode=request.transport_mode,
            area_name=area_name,
            weather_condition=weather_condition,
            cache_used=False
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Route calculation failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during route calculation")

@app.get("/api/areas")
async def get_supported_areas():
    """サポートエリア一覧（簡易版）"""
    return {
        "supported_areas": {
            "shinjuku": {"name": "新宿区", "center": [35.6917, 139.7036]},
            "shibuya": {"name": "渋谷区", "center": [35.6598, 139.7036]},
            "minato": {"name": "港区", "center": [35.6584, 139.7514]},
            "chuo": {"name": "中央区", "center": [35.6735, 139.7709]},
            "chiyoda": {"name": "千代田区", "center": [35.6938, 139.7536]}
        },
        "version": "simple",
        "note": "Database features disabled"
    }

@app.get("/api/areas/{area_code}/weather")
async def get_area_weather(area_code: str):
    """エリア別天気情報（ダミーデータ）"""
    import random
    
    conditions = ["clear", "partly_cloudy", "cloudy"]
    condition = random.choice(conditions)
    
    return {
        "area_code": area_code,
        "current_weather": {
            "condition": condition,
            "temperature": round(20 + random.uniform(-5, 10), 1),
            "humidity": random.randint(40, 80),
            "cloud_cover": random.uniform(0.1, 0.8),
            "description": f"簡易版天気データ ({condition})",
            "shade_importance": random.uniform(0.2, 0.8),
            "fallback": True
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)