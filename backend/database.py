from motor.motor_asyncio import AsyncIOMotorClient
import os

_client = None
_db = None


def get_db():
    return _db


async def init_db():
    global _client, _db
    _client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    _db = _client[os.environ['DB_NAME']]
    return _db


async def close_db():
    global _client
    if _client:
        _client.close()
