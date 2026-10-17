from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReadPreference
import os

_client = None
_db = None


def get_db():
    return _db


async def init_db():
    global _client, _db
    _client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    # Authorization, active status and MFA must not use lagging secondary reads.
    _db = _client.get_database(os.environ['DB_NAME'], read_preference=ReadPreference.PRIMARY)
    return _db


async def close_db():
    global _client
    if _client:
        _client.close()
