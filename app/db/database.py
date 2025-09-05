# MongoDB connection logic
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from fastapi import Request, Depends
from app.core.config import settings
from typing import Callable

async def connect_to_mongo(app):
    """Connects to MongoDB and stores the client in app.state."""
    app.state.mongo_client = AsyncIOMotorClient(settings.MONGO_URI)
    print("MongoDB connection opened.")

async def close_mongo_connection(app):
    """Closes the MongoDB connection."""
    if hasattr(app.state, 'mongo_client') and app.state.mongo_client:
        app.state.mongo_client.close()
        print("MongoDB connection closed.")

def get_db(request: Request) -> AsyncIOMotorDatabase:
    """Dependency to get the database instance from the request state."""
    client: AsyncIOMotorClient = request.app.state.mongo_client
    return client[settings.AYUSHMITRA]

# You can also place your helper for fetching collections here
def get_collection(name: str) -> Callable[[AsyncIOMotorDatabase], AsyncIOMotorCollection]:
    """
    Returns a dependency that provides a collection.
    """
    def dependency(db: AsyncIOMotorDatabase = Depends(get_db)) -> AsyncIOMotorCollection:
        return db[name]
    return dependency
