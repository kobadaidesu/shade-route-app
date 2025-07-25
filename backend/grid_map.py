"""
グリッドベースの地図表現とダイクストラ法による最適ルート探索
"""
import heapq
import math
import logging
from typing import List, Tuple, Dict, Optional, Set
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import asyncio

from config import map_config, performance_config
from building_service import building_service
from models import Building

logger = logging.getLogger(__name__)

@dataclass
class GridCell:
    """グリッドセル"""
    x: int
    y: int
    lon: float
    lat: float
    shade_cost: float = 0.0
    is_blocked: bool = False
    building_id: Optional[int] = None
    
    def __hash__(self):
        return hash((self.x, self.y))
    
    def __eq__(self, other):
        return self.x == other.x and self.y == other.y

@dataclass
class PathNode:
    """ダイクストラ法用のノード"""
    cell: GridCell
    cost: float
    parent: Optional['PathNode'] = None
    
    def __lt__(self, other):
        return self.cost < other.cost

class GridMap:
    """グリッドマップ"""
    
    def __init__(self, 
                 bbox: Tuple[float, float, float, float],
                 grid_size: float = 0.0001):  # 約10m
        """
        Args:
            bbox: 境界ボックス (south, west, north, east)
            grid_size: グリッドサイズ（度）
        """
        self.bbox = bbox
        self.grid_size = grid_size
        self.south, self.west, self.north, self.east = bbox
        
        # グリッドのサイズを計算
        self.grid_width = int((self.east - self.west) / grid_size) + 1
        self.grid_height = int((self.north - self.south) / grid_size) + 1
        
        # グリッドセルの初期化
        self.grid: List[List[GridCell]] = []
        self._initialize_grid()
        
        logger.info(f"Grid initialized: {self.grid_width}x{self.grid_height} cells")
    
    def _initialize_grid(self):
        """グリッドを初期化"""
        for y in range(self.grid_height):
            row = []
            for x in range(self.grid_width):
                lon = self.west + x * self.grid_size
                lat = self.south + y * self.grid_size
                
                cell = GridCell(x=x, y=y, lon=lon, lat=lat)
                row.append(cell)
            self.grid.append(row)
    
    def get_cell(self, x: int, y: int) -> Optional[GridCell]:
        """グリッドセルを取得"""
        if 0 <= x < self.grid_width and 0 <= y < self.grid_height:
            return self.grid[y][x]
        return None
    
    def coord_to_grid(self, lon: float, lat: float) -> Tuple[int, int]:
        """座標をグリッドインデックスに変換"""
        x = int((lon - self.west) / self.grid_size)
        y = int((lat - self.south) / self.grid_size)
        return max(0, min(x, self.grid_width - 1)), max(0, min(y, self.grid_height - 1))
    
    def grid_to_coord(self, x: int, y: int) -> Tuple[float, float]:
        """グリッドインデックスを座標に変換"""
        lon = self.west + x * self.grid_size
        lat = self.south + y * self.grid_size
        return lon, lat
    
    def get_neighbors(self, cell: GridCell) -> List[GridCell]:
        """隣接セルを取得（8方向）"""
        neighbors = []
        directions = [
            (-1, -1), (-1, 0), (-1, 1),
            (0, -1),           (0, 1),
            (1, -1),  (1, 0),  (1, 1)
        ]
        
        for dx, dy in directions:
            nx, ny = cell.x + dx, cell.y + dy
            neighbor = self.get_cell(nx, ny)
            if neighbor and not neighbor.is_blocked:
                neighbors.append(neighbor)
        
        return neighbors
    
    def calculate_distance(self, cell1: GridCell, cell2: GridCell) -> float:
        """2つのセル間の距離を計算"""
        dx = abs(cell1.x - cell2.x)
        dy = abs(cell1.y - cell2.y)
        
        # 対角線移動の場合
        if dx == 1 and dy == 1:
            return math.sqrt(2) * self.grid_size * 111000  # メートル換算
        else:
            return math.sqrt(dx*dx + dy*dy) * self.grid_size * 111000
    
    async def update_with_buildings(self, buildings: List[Building], time_str: str):
        """建物データでグリッドを更新"""
        logger.info(f"Updating grid with {len(buildings)} buildings...")
        
        # 並列処理でセルを更新
        tasks = []
        for y in range(self.grid_height):
            for x in range(self.grid_width):
                cell = self.grid[y][x]
                task = self._update_cell_with_buildings(cell, buildings, time_str)
                tasks.append(task)
        
        # バッチ処理で効率化
        batch_size = 100
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            await asyncio.gather(*batch)
        
        logger.info("Grid update completed")
    
    async def _update_cell_with_buildings(self, cell: GridCell, buildings: List[Building], time_str: str):
        """セルを建物データで更新"""
        try:
            # 建物内かチェック
            if building_service.is_point_in_building(cell.lon, cell.lat, buildings):
                cell.is_blocked = True
                cell.shade_cost = float('inf')
                return
            
            # 日陰率を計算
            loop = asyncio.get_event_loop()
            shadow_factor = await loop.run_in_executor(
                None,
                building_service.calculate_shadow_factor,
                cell.lon, cell.lat, time_str, buildings
            )
            
            # 基本的な日陰率を加算
            base_shade = self._calculate_base_shade(cell.lon, cell.lat, time_str)
            total_shade = min(1.0, shadow_factor + base_shade)
            
            # 日陰率をコストに変換（日陰が少ないほうが良い）
            cell.shade_cost = 1.0 - total_shade  # 0.0-1.0、低いほど良い
            
        except Exception as e:
            logger.error(f"Error updating cell ({cell.x}, {cell.y}): {e}")
            cell.shade_cost = 0.5  # デフォルト値
    
    def _calculate_base_shade(self, lon: float, lat: float, time_str: str) -> float:
        """基本的な日陰率を計算"""
        try:
            hour = int(time_str.split(":")[0])
            
            # 夜間は完全な日陰（100%）
            if hour < 6 or hour > 18:
                return 1.0
            
            # 薄明時間帯の処理
            if hour == 6 or hour == 18:
                return 0.8  # 薄明時は80%の日陰
            
            # 日中の基本日陰率（建物以外の自然な日陰）
            time_factor = 0.1 + 0.05 * math.sin((hour - 12) * math.pi / 6)
            
            # 位置による調整（最小限）
            center_lon, center_lat = map_config.shinjuku_station_location[1], map_config.shinjuku_station_location[0]
            position_factor = ((lat - center_lat) * 1 + (lon - center_lon) * 0.3) * 0.05
            
            return max(0.0, min(0.3, time_factor + position_factor))  # 最大30%に制限
        except:
            return 0.2

class DijkstraPathfinder:
    """ダイクストラ法による経路探索"""
    
    def __init__(self, grid_map: GridMap):
        self.grid_map = grid_map
    
    def find_path(self, start_coord: Tuple[float, float], 
                  end_coord: Tuple[float, float],
                  weight_shade: float = 0.7,
                  weight_distance: float = 0.3) -> Optional[List[GridCell]]:
        """
        ダイクストラ法でパスを探索
        
        Args:
            start_coord: 開始座標 (lon, lat)
            end_coord: 終了座標 (lon, lat)
            weight_shade: 日陰重み
            weight_distance: 距離重み
            
        Returns:
            パスのセルリスト
        """
        # 開始・終了セルを取得
        start_x, start_y = self.grid_map.coord_to_grid(*start_coord)
        end_x, end_y = self.grid_map.coord_to_grid(*end_coord)
        
        start_cell = self.grid_map.get_cell(start_x, start_y)
        end_cell = self.grid_map.get_cell(end_x, end_y)
        
        if not start_cell or not end_cell:
            logger.error("Invalid start or end coordinates")
            return None
        
        if start_cell.is_blocked or end_cell.is_blocked:
            logger.error("Start or end cell is blocked")
            return None
        
        # ダイクストラ法
        heap = [PathNode(start_cell, 0.0)]
        visited: Set[GridCell] = set()
        distances: Dict[GridCell, float] = {start_cell: 0.0}
        parents: Dict[GridCell, Optional[GridCell]] = {start_cell: None}
        
        while heap:
            current_node = heapq.heappop(heap)
            current_cell = current_node.cell
            
            if current_cell in visited:
                continue
            
            visited.add(current_cell)
            
            # 終了条件
            if current_cell == end_cell:
                return self._reconstruct_path(parents, start_cell, end_cell)
            
            # 隣接セルを探索
            for neighbor in self.grid_map.get_neighbors(current_cell):
                if neighbor in visited:
                    continue
                
                # コスト計算
                distance_cost = self.grid_map.calculate_distance(current_cell, neighbor)
                shade_cost = neighbor.shade_cost * 1000  # スケール調整
                
                # 重み付きコスト
                total_cost = (weight_distance * distance_cost + 
                             weight_shade * shade_cost)
                
                new_distance = distances[current_cell] + total_cost
                
                if neighbor not in distances or new_distance < distances[neighbor]:
                    distances[neighbor] = new_distance
                    parents[neighbor] = current_cell
                    heapq.heappush(heap, PathNode(neighbor, new_distance))
        
        logger.warning("No path found")
        return None
    
    def _reconstruct_path(self, parents: Dict[GridCell, Optional[GridCell]], 
                         start: GridCell, end: GridCell) -> List[GridCell]:
        """パスを再構築"""
        path = []
        current = end
        
        while current is not None:
            path.append(current)
            current = parents[current]
        
        path.reverse()
        return path
    
    def smooth_path(self, path: List[GridCell], smoothing_factor: int = 3) -> List[GridCell]:
        """パスをスムージング"""
        if len(path) <= 2:
            return path
        
        smoothed = [path[0]]
        
        for i in range(1, len(path) - 1):
            # 前後の点を考慮してスムージング
            prev_cell = path[i-1]
            current_cell = path[i]
            next_cell = path[i+1]
            
            # 直線上にある場合はスキップ
            if self._is_collinear(prev_cell, current_cell, next_cell):
                continue
            
            smoothed.append(current_cell)
        
        smoothed.append(path[-1])
        return smoothed
    
    def _is_collinear(self, a: GridCell, b: GridCell, c: GridCell) -> bool:
        """3点が直線上にあるかチェック"""
        # 外積を使用して共線性をチェック
        cross_product = (c.y - a.y) * (b.x - a.x) - (b.y - a.y) * (c.x - a.x)
        return abs(cross_product) < 1e-10

# グローバルインスタンス
grid_map_cache: Dict[str, GridMap] = {}

def get_grid_map(bbox: Tuple[float, float, float, float], 
                 grid_size: float = 0.0001) -> GridMap:
    """グリッドマップを取得（キャッシュ利用）"""
    cache_key = f"{bbox}_{grid_size}"
    
    if cache_key not in grid_map_cache:
        grid_map_cache[cache_key] = GridMap(bbox, grid_size)
    
    return grid_map_cache[cache_key]