# MongoDB connection logic
from pymongo import MongoClient
from app.core.config import settings

client: MongoClient = None

def get_db():
    if client is None:
        raise Exception("Database client not initialized. Call connect_to_mongo first.")
    return client[settings.AYUSHMITRA]

async def connect_to_mongo():
    global client
    print("Connecting to MongoDB...")
    client = MongoClient(settings.MONGO_URI)
    print("Successfully connected to MongoDB.")

async def close_mongo_connection():
    global client
    if client:
        client.close()
        print("MongoDB connection closed.")

# You can also place your helper for fetching collections here
def get_collection(name: str):
    return get_db()[name]
