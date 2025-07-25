"""
最適化された統合APIサーバー
パフォーマンスとコード品質を大幅に改善
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from config import api_config, performance_config
from cache_manager import cache_manager
from building_service import building_service
from route_service import route_service
from dijkstra_route_service import dijkstra_route_service
from realtime_service import realtime_shade_service
from models import (
    RouteRequest, RouteResponse, BuildingCollection, 
    HealthResponse, ErrorResponse, CacheStats
)
from custom_node_service import (
    custom_node_service, CustomNodeCreate, CustomNodeResponse
)

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクル管理"""
    logger.info("Starting Shade Route API Server...")
    
    # 起動時の処理
    yield
    
    # シャットダウン時の処理
    logger.info("Shutting down Shade Route API Server...")
    await building_service.close()
    cache_manager.clear_all()

# FastAPIアプリケーション
app = FastAPI(
    title=api_config.title,
    version=api_config.version,
    description="最適化された日陰回避ルート検索API",
    lifespan=lifespan
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 開発環境では全てのオリジンを許可
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# リクエスト処理時間のミドルウェア
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """リクエスト処理時間を記録"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# グローバル例外ハンドラー
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """グローバル例外ハンドラー"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    error_response = ErrorResponse(
        error="internal_server_error",
        message="内部サーバーエラーが発生しました",
        details={"request_path": str(request.url.path)},
        timestamp=datetime.now().isoformat()
    )
    
    return JSONResponse(
        status_code=500,
        content=error_response.dict()
    )

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """ヘルスチェック"""
    try:
        cache_stats = cache_manager.stats()
        
        return HealthResponse(
            status="healthy",
            timestamp=datetime.now().isoformat(),
            version=api_config.version,
            cache_stats=cache_stats
        )
    except Exception as e:
        logger.error(f"Health check error: {e}")
        raise HTTPException(
            status_code=500,
            detail="ヘルスチェックに失敗しました"
        )

@app.get("/api/stats")
async def get_stats():
    """システム統計情報"""
    try:
        stats = {
            "cache": cache_manager.stats(),
            "config": {
                "max_workers": performance_config.max_workers,
                "route_points_count": performance_config.route_points_count,
                "cache_ttl": performance_config.external_api_timeout
            },
            "timestamp": datetime.now().isoformat()
        }
        return stats
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(
            status_code=500,
            detail="統計情報の取得に失敗しました"
        )

@app.post("/api/cache/clear")
async def clear_cache():
    """キャッシュクリア"""
    try:
        cache_manager.clear_all()
        return {"message": "キャッシュをクリアしました"}
    except Exception as e:
        logger.error(f"Cache clear error: {e}")
        raise HTTPException(
            status_code=500,
            detail="キャッシュクリアに失敗しました"
        )

@app.get("/api/buildings", response_model=BuildingCollection)
async def get_buildings():
    """建物データを取得"""
    try:
        start_time = time.time()
        buildings = await building_service.get_buildings()
        processing_time = time.time() - start_time
        
        logger.info(f"Buildings retrieved: {len(buildings.features)} items in {processing_time:.2f}s")
        return buildings
        
    except Exception as e:
        logger.error(f"Building retrieval error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"建物データの取得に失敗しました: {str(e)}"
        )

@app.post("/api/route/shade-avoid", response_model=RouteResponse)
async def calculate_shade_avoiding_route(request: RouteRequest):
    """日陰回避ルートを計算"""
    try:
        # リクエストのバリデーション
        if not request.start or not request.end:
            raise HTTPException(
                status_code=400,
                detail="開始地点と終了地点を指定してください"
            )
        
        # 座標範囲チェック（東京近郊）
        for point in [request.start, request.end]:
            lon, lat = point
            if not (139.0 <= lon <= 140.0 and 35.0 <= lat <= 36.0):
                raise HTTPException(
                    status_code=400,
                    detail="東京近郊の座標を指定してください"
                )
        
        # ルート計算
        route_response = await route_service.calculate_route(request)
        
        return route_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Route calculation error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"ルート計算に失敗しました: {str(e)}"
        )

@app.post("/api/route/dijkstra", response_model=RouteResponse)
async def calculate_dijkstra_route(request: RouteRequest):
    """ダイクストラ法で最適ルートを計算"""
    try:
        # リクエストのバリデーション
        if not request.start or not request.end:
            raise HTTPException(
                status_code=400,
                detail="開始地点と終了地点を指定してください"
            )
        
        # 座標範囲チェック（東京近郊）
        for point in [request.start, request.end]:
            lon, lat = point
            if not (139.0 <= lon <= 140.0 and 35.0 <= lat <= 36.0):
                raise HTTPException(
                    status_code=400,
                    detail="東京近郊の座標を指定してください"
                )
        
        # ダイクストラ法でルート計算
        route_response = await dijkstra_route_service.calculate_optimal_route(request)
        
        return route_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dijkstra route calculation error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"ダイクストラ法によるルート計算に失敗しました: {str(e)}"
        )

@app.post("/api/route/compare")
async def compare_routes(request: RouteRequest):
    """シンプル法とダイクストラ法を比較"""
    try:
        # リクエストのバリデーション
        if not request.start or not request.end:
            raise HTTPException(
                status_code=400,
                detail="開始地点と終了地点を指定してください"
            )
        
        # 両方の方法で計算して比較
        comparison = await dijkstra_route_service.compare_routes(request)
        
        return comparison
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Route comparison error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"ルート比較に失敗しました: {str(e)}"
        )

@app.get("/api/shade/hourly")
async def get_hourly_shade_predictions(
    lon: float,
    lat: float,
    date: str = None
):
    """1日の時間別日陰予測を取得"""
    try:
        predictions = await realtime_shade_service.get_hourly_predictions(lon, lat, date)
        
        return {
            "location": {"longitude": lon, "latitude": lat},
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "predictions": [
                {
                    "time": p.time,
                    "shade_ratio": p.shade_ratio,
                    "sun_elevation": p.sun_elevation,
                    "sun_azimuth": p.sun_azimuth
                }
                for p in predictions
            ]
        }
        
    except Exception as e:
        logger.error(f"Hourly shade predictions error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"時間別日陰予測の取得に失敗しました: {str(e)}"
        )

@app.get("/api/shade/current")
async def get_current_shade_info(lon: float, lat: float):
    """現在の日陰情報を取得"""
    try:
        current_info = await realtime_shade_service.get_current_shade_update(lon, lat)
        return current_info
        
    except Exception as e:
        logger.error(f"Current shade info error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"現在の日陰情報の取得に失敗しました: {str(e)}"
        )

@app.post("/api/shade/timeline")
async def get_route_shade_timeline(route_points: List[Dict[str, float]], date: str = None):
    """ルート全体の時間別日陰変化を取得"""
    try:
        from models import RoutePoint
        
        # 辞書をRoutePointオブジェクトに変換
        points = [
            RoutePoint(
                longitude=point["longitude"],
                latitude=point["latitude"],
                shade_ratio=point.get("shade_ratio", 0.0)
            )
            for point in route_points
        ]
        
        timeline = await realtime_shade_service.get_route_shade_timeline(points, date)
        
        return {
            "route_points_count": len(points),
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "timeline": timeline
        }
        
    except Exception as e:
        logger.error(f"Route shade timeline error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"ルート日陰タイムラインの取得に失敗しました: {str(e)}"
        )

@app.get("/api/route/direct")
async def calculate_direct_route(
    start_lon: float,
    start_lat: float,
    end_lon: float,
    end_lat: float,
    time: str = "12:00",
    transport_mode: str = "walk"
):
    """直線ルートを計算（デバッグ用）"""
    try:
        request = RouteRequest(
            start=[start_lon, start_lat],
            end=[end_lon, end_lat],
            time=time,
            date=datetime.now().strftime("%Y-%m-%d"),
            transport_mode=transport_mode
        )
        
        return await calculate_shade_avoiding_route(request)
        
    except Exception as e:
        logger.error(f"Direct route calculation error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"直線ルート計算に失敗しました: {str(e)}"
        )


# カスタムノード管理エンドポイント
@app.post("/api/custom-nodes", response_model=CustomNodeResponse)
async def create_custom_node(node: CustomNodeCreate):
    """新しいカスタムノードを作成"""
    try:
        # 座標範囲チェック（東京近郊）
        if not (139.0 <= node.lng <= 140.0 and 35.0 <= node.lat <= 36.0):
            raise HTTPException(
                status_code=400,
                detail="東京近郊の座標を指定してください"
            )
        
        created_node = custom_node_service.create_node(node)
        logger.info(f"Created custom node: {created_node.name} by {created_node.created_by}")
        
        return created_node
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Custom node creation error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"カスタムノードの作成に失敗しました: {str(e)}"
        )

@app.get("/api/custom-nodes", response_model=List[CustomNodeResponse])
async def get_custom_nodes(created_by: str = None):
    """カスタムノード一覧を取得"""
    try:
        if created_by:
            nodes = custom_node_service.get_nodes_by_creator(created_by)
        else:
            nodes = custom_node_service.get_all_nodes()
        
        logger.info(f"Retrieved {len(nodes)} custom nodes")
        return nodes
        
    except Exception as e:
        logger.error(f"Custom nodes retrieval error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"カスタムノードの取得に失敗しました: {str(e)}"
        )

@app.get("/api/custom-nodes/{node_id}", response_model=CustomNodeResponse)
async def get_custom_node(node_id: int):
    """特定のカスタムノードを取得"""
    try:
        node = custom_node_service.get_node(node_id)
        if not node:
            raise HTTPException(
                status_code=404,
                detail="カスタムノードが見つかりません"
            )
        
        return node
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Custom node retrieval error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"カスタムノードの取得に失敗しました: {str(e)}"
        )

@app.put("/api/custom-nodes/{node_id}", response_model=CustomNodeResponse)
async def update_custom_node(node_id: int, node: CustomNodeCreate):
    """カスタムノードを更新"""
    try:
        # 座標範囲チェック（東京近郊）
        if not (139.0 <= node.lng <= 140.0 and 35.0 <= node.lat <= 36.0):
            raise HTTPException(
                status_code=400,
                detail="東京近郊の座標を指定してください"
            )
        
        updated_node = custom_node_service.update_node(node_id, node)
        if not updated_node:
            raise HTTPException(
                status_code=404,
                detail="カスタムノードが見つかりません"
            )
        
        logger.info(f"Updated custom node: {updated_node.name}")
        return updated_node
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Custom node update error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"カスタムノードの更新に失敗しました: {str(e)}"
        )

@app.delete("/api/custom-nodes/{node_id}")
async def delete_custom_node(node_id: int):
    """カスタムノードを削除"""
    try:
        success = custom_node_service.delete_node(node_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail="カスタムノードが見つかりません"
            )
        
        logger.info(f"Deleted custom node ID: {node_id}")
        return {"message": "カスタムノードを削除しました"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Custom node deletion error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"カスタムノードの削除に失敗しました: {str(e)}"
        )

@app.get("/api/custom-nodes/bounds")
async def get_custom_nodes_in_bounds(north: float, south: float, east: float, west: float):
    """範囲内のカスタムノードを取得"""
    try:
        nodes = custom_node_service.get_nodes_in_bounds(north, south, east, west)
        logger.info(f"Retrieved {len(nodes)} custom nodes in bounds")
        return nodes
        
    except Exception as e:
        logger.error(f"Custom nodes bounds retrieval error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"範囲内カスタムノードの取得に失敗しました: {str(e)}"
        )

# デバッグ用エンドポイント
@app.get("/api/debug/config")
async def get_config():
    """設定情報を取得（デバッグ用）"""
    return {
        "api_config": {
            "host": api_config.host,
            "port": api_config.port,
            "cors_origins": api_config.cors_origins
        },
        "performance_config": {
            "max_workers": performance_config.max_workers,
            "route_points_count": performance_config.route_points_count,
            "external_api_timeout": performance_config.external_api_timeout
        }
    }

def main():
    """メイン関数"""
    logger.info(f"Starting server on {api_config.host}:{api_config.port}")
    
    uvicorn.run(
        "main_optimized:app",
        host=api_config.host,
        port=api_config.port,
        reload=False,
        workers=1,  # 非同期処理を活用するため単一ワーカー
        loop="asyncio",
        log_level="info"
    )

if __name__ == "__main__":
    main()