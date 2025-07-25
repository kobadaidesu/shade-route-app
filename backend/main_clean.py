"""
クリーンで安定したAPI
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import datetime
import logging
import math

logging.basicConfig(level=logging.INFO)

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

def calculate_shade_ratio(lon: float, lat: float, time_str: str) -> float:
    """シンプルな日陰率計算"""
    try:
        hour = int(time_str.split(":")[0])
        
        # 時間帯による基本日陰
        base_shade = 0.3 + 0.2 * math.sin((hour - 6) * math.pi / 12)
        
        # 位置による調整
        position_factor = (lat - 35.69) * 2 + (lon - 139.70) * 0.5
        
        # 総合日陰率
        total_shade = base_shade + position_factor * 0.1
        return max(0.0, min(1.0, total_shade))
        
    except Exception:
        return 0.3  # デフォルト値

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat()}

@app.post("/api/route/shade-avoid", response_model=RouteResponse)
async def calculate_shade_avoiding_route(request: RouteRequest):
    try:
        start_lon, start_lat = request.start
        end_lon, end_lat = request.end
        
        # シンプルな直線ルート生成
        route_points = []
        num_points = 20
        
        for i in range(num_points + 1):
            ratio = i / num_points
            lon = start_lon + (end_lon - start_lon) * ratio
            lat = start_lat + (end_lat - start_lat) * ratio
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
        avg_shade = sum(p.shade_ratio for p in route_points) / len(route_points) if route_points else 0.3
        
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
            area_name="新宿区",
            weather_condition="partly_cloudy",
            cache_used=False
        )
        
    except Exception as e:
        logging.error(f"Route calculation error: {e}")
        raise HTTPException(status_code=500, detail=f"Route calculation failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)