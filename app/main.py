# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv
import os
from contextlib import asynccontextmanager
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Setup application lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup...")
    from app.db.database import connect_to_mongo, close_mongo_connection
    await connect_to_mongo(app)
    yield
    logger.info("Application shutdown...")
    await close_mongo_connection(app)

# Create FastAPI app
app = FastAPI(
    title="AyurCare API",
    description="API for AyurCare application with doctor and patient roles",
    version="0.1.0",
    lifespan=lifespan
)

# Configure CORS
origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "*" # Allow all for hackathon
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from app.api.router import doctors, patients

# app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(doctors.router, prefix="/doctors", tags=["Doctors"])
app.include_router(patients.router, prefix="/patients", tags=["Patients"])


@app.get("/", tags=["Health"])
async def root():
    return {"message": "Welcome to AyurCare API"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)