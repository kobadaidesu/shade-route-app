"""
キャッシュマネージャー - メモリ効率的なキャッシュ管理
"""
import time
import logging
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass

from config import cache_config

logger = logging.getLogger(__name__)

@dataclass
class CacheItem:
    """キャッシュアイテム"""
    value: Any
    timestamp: float
    access_count: int = 0
    
    def is_expired(self, ttl_seconds: int) -> bool:
        """有効期限切れかチェック"""
        return time.time() - self.timestamp > ttl_seconds
    
    def access(self):
        """アクセス記録"""
        self.access_count += 1

class LRUCache:
    """LRUキャッシュ実装（スレッドセーフ）"""
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheItem] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        
    def get(self, key: str) -> Optional[Any]:
        """キーの値を取得"""
        with self._lock:
            item = self._cache.get(key)
            if item is None:
                self._misses += 1
                return None
            
            # 有効期限チェック
            if item.is_expired(self.ttl_seconds):
                del self._cache[key]
                self._misses += 1
                return None
            
            # アクセス記録とLRU更新
            item.access()
            self._cache.move_to_end(key)
            self._hits += 1
            return item.value
    
    def put(self, key: str, value: Any) -> None:
        """キーに値を設定"""
        with self._lock:
            current_time = time.time()
            
            if key in self._cache:
                # 既存キーの更新
                self._cache[key].value = value
                self._cache[key].timestamp = current_time
                self._cache.move_to_end(key)
            else:
                # 新規キー
                if len(self._cache) >= self.max_size:
                    # 最古のアイテムを削除
                    oldest_key = next(iter(self._cache))
                    del self._cache[oldest_key]
                    logger.debug(f"Evicted cache item: {oldest_key}")
                
                self._cache[key] = CacheItem(value, current_time)
    
    def clear(self) -> None:
        """キャッシュをクリア"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def size(self) -> int:
        """キャッシュサイズを取得"""
        with self._lock:
            return len(self._cache)
    
    def hit_rate(self) -> float:
        """ヒット率を取得"""
        with self._lock:
            total = self._hits + self._misses
            return self._hits / total if total > 0 else 0.0
    
    def cleanup_expired(self) -> int:
        """期限切れアイテムをクリーンアップ"""
        with self._lock:
            current_time = time.time()
            expired_keys = []
            
            for key, item in self._cache.items():
                if item.is_expired(self.ttl_seconds):
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._cache[key]
            
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache items")
            return len(expired_keys)
    
    def stats(self) -> Dict[str, Any]:
        """キャッシュ統計を取得"""
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self.hit_rate(),
                "ttl_seconds": self.ttl_seconds
            }

class CacheManager:
    """キャッシュマネージャー"""
    
    def __init__(self):
        self.building_cache = LRUCache(
            max_size=cache_config.max_cache_size,
            ttl_seconds=cache_config.cache_ttl_seconds
        )
        self.route_cache = LRUCache(
            max_size=cache_config.max_cache_size * 2,  # ルートキャッシュは多めに
            ttl_seconds=cache_config.cache_ttl_seconds // 2  # ルートキャッシュは短めに
        )
        self._cleanup_thread = None
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        """クリーンアップスレッドを開始"""
        if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_worker,
                daemon=True
            )
            self._cleanup_thread.start()
    
    def _cleanup_worker(self):
        """定期的なクリーンアップワーカー"""
        while True:
            time.sleep(300)  # 5分ごとにクリーンアップ
            try:
                building_cleaned = self.building_cache.cleanup_expired()
                route_cleaned = self.route_cache.cleanup_expired()
                
                if building_cleaned > 0 or route_cleaned > 0:
                    logger.info(f"Cache cleanup: {building_cleaned} building items, {route_cleaned} route items")
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")
    
    def get_buildings(self, cache_key: str) -> Optional[Dict]:
        """建物データを取得"""
        if not cache_config.building_cache_enabled:
            return None
        return self.building_cache.get(cache_key)
    
    def set_buildings(self, cache_key: str, buildings: Dict) -> None:
        """建物データを保存"""
        if cache_config.building_cache_enabled:
            self.building_cache.put(cache_key, buildings)
    
    def get_route(self, cache_key: str) -> Optional[Dict]:
        """ルートデータを取得"""
        if not cache_config.route_cache_enabled:
            return None
        return self.route_cache.get(cache_key)
    
    def set_route(self, cache_key: str, route: Dict) -> None:
        """ルートデータを保存"""
        if cache_config.route_cache_enabled:
            self.route_cache.put(cache_key, route)
    
    def clear_all(self) -> None:
        """全キャッシュをクリア"""
        self.building_cache.clear()
        self.route_cache.clear()
    
    def stats(self) -> Dict[str, Any]:
        """キャッシュ統計を取得"""
        return {
            "building_cache": self.building_cache.stats(),
            "route_cache": self.route_cache.stats()
        }

# グローバルキャッシュマネージャー
cache_manager = CacheManager()