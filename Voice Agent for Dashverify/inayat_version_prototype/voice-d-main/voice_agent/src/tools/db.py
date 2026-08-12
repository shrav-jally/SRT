import logging
import json
import asyncio
import os
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class MockDB:
    """
    JSON-file backed asynchronous database operations.
    """
    def __init__(self, db_path: str = "data.json"):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        
        # Initialize file if not exists
        if not os.path.exists(self.db_path):
            with open(self.db_path, "w") as f:
                json.dump({}, f)

    async def _read_db(self) -> Dict[str, Any]:
        async with self._lock:
            try:
                with open(self.db_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading DB: {e}")
                return {}

    async def _write_db(self, data: Dict[str, Any]) -> bool:
        async with self._lock:
            try:
                with open(self.db_path, "w") as f:
                    json.dump(data, f, indent=4)
                return True
            except Exception as e:
                logger.error(f"Error writing DB: {e}")
                return False

    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        logger.info(f"DB Read: get_user_profile for {user_id}")
        data = await self._read_db()
        return data.get(user_id, {"user_id": user_id, "name": "Test User", "status": "active"})

    async def save_interaction(self, user_id: str, interaction_data: Dict[str, Any]) -> bool:
        logger.info(f"DB Write: save_interaction for {user_id}")
        data = await self._read_db()
        
        if user_id not in data:
            data[user_id] = {"interactions": []}
            
        data[user_id].setdefault("interactions", []).append(interaction_data)
        
        return await self._write_db(data)

