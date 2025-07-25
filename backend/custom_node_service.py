"""
カスタムノード管理サービス
SQLiteデータベースを使用してカスタムノードを永続化
"""
import sqlite3
import json
from typing import List, Optional
from datetime import datetime
import os
from pydantic import BaseModel

class CustomNodeCreate(BaseModel):
    lat: float
    lng: float
    name: str
    type: str
    description: Optional[str] = None
    created_by: Optional[str] = "anonymous"
    icon_type: Optional[str] = "circle"
    color: Optional[str] = "#8b5cf6"

class CustomNodeResponse(BaseModel):
    id: int
    lat: float
    lng: float
    name: str
    type: str
    description: Optional[str]
    created_by: str
    created_at: str
    icon_type: Optional[str]
    color: Optional[str]

class CustomNodeService:
    def __init__(self, db_path: str = "custom_nodes.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """データベース初期化"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS custom_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lat REAL NOT NULL,
                    lng REAL NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT,
                    created_by TEXT DEFAULT 'anonymous',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    icon_type TEXT DEFAULT 'circle',
                    color TEXT DEFAULT '#8b5cf6'
                )
            """)
            conn.commit()
    
    def create_node(self, node: CustomNodeCreate) -> CustomNodeResponse:
        """新しいカスタムノードを作成"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO custom_nodes (lat, lng, name, type, description, created_by, icon_type, color)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (node.lat, node.lng, node.name, node.type, node.description, node.created_by, node.icon_type, node.color))
            
            node_id = cursor.lastrowid
            conn.commit()
            
            # 作成されたノードを取得
            return self.get_node(node_id)
    
    def get_node(self, node_id: int) -> Optional[CustomNodeResponse]:
        """IDでノードを取得"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM custom_nodes WHERE id = ?
            """, (node_id,))
            
            row = cursor.fetchone()
            if row:
                return CustomNodeResponse(**dict(row))
            return None
    
    def get_all_nodes(self) -> List[CustomNodeResponse]:
        """全てのカスタムノードを取得"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM custom_nodes ORDER BY created_at DESC
            """)
            
            rows = cursor.fetchall()
            return [CustomNodeResponse(**dict(row)) for row in rows]
    
    def update_node(self, node_id: int, node: CustomNodeCreate) -> Optional[CustomNodeResponse]:
        """ノード情報を更新"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE custom_nodes 
                SET lat = ?, lng = ?, name = ?, type = ?, description = ?, icon_type = ?, color = ?
                WHERE id = ?
            """, (node.lat, node.lng, node.name, node.type, node.description, node.icon_type, node.color, node_id))
            
            if cursor.rowcount > 0:
                conn.commit()
                return self.get_node(node_id)
            return None
    
    def delete_node(self, node_id: int) -> bool:
        """ノードを削除"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM custom_nodes WHERE id = ?
            """, (node_id,))
            
            success = cursor.rowcount > 0
            conn.commit()
            return success
    
    def get_nodes_by_creator(self, created_by: str) -> List[CustomNodeResponse]:
        """作成者でフィルタリング"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM custom_nodes WHERE created_by = ? ORDER BY created_at DESC
            """, (created_by,))
            
            rows = cursor.fetchall()
            return [CustomNodeResponse(**dict(row)) for row in rows]
    
    def get_nodes_in_bounds(self, north: float, south: float, east: float, west: float) -> List[CustomNodeResponse]:
        """範囲内のノードを取得"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM custom_nodes 
                WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?
                ORDER BY created_at DESC
            """, (south, north, west, east))
            
            rows = cursor.fetchall()
            return [CustomNodeResponse(**dict(row)) for row in rows]

# グローバルインスタンス
custom_node_service = CustomNodeService()