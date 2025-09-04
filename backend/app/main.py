from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv
import os
from contextlib import asynccontextmanager

# Load environment variables
load_dotenv()

# Setup application lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect to database
    from db_mongo import get_database
    get_database()
    yield
    # Shutdown: Nothing to clean up yet

# Create FastAPI app
app = FastAPI(
    title="AyurCare API",
    description="API for AyurCare application with doctor and patient roles",
    version="0.1.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from routes.auth import router as auth_router
from routes.users import router as users_router

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(users_router, prefix="/users", tags=["Users"])

@app.get("/", tags=["Health"])
async def root():
    return {"message": "Welcome to AyurCare API"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
