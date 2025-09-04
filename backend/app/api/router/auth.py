from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from backend.app.core.security import verify_password, get_password_hash, create_access_token
from backend.db_mongo import get_database
from backend.app.models.user_models import UserPublic
from datetime import timedelta

router = APIRouter(prefix="/auth", tags=["auth"])

class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/register", response_model=UserPublic)
async def register_user(request: RegisterRequest):
    db = get_database()
    existing = await db["users"].find_one({"email": request.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = {
        "email": request.email,
        "hashed_password": get_password_hash(request.password),
        "role": request.role,
        "first_name": "",  # You may want to collect these in RegisterRequest
        "last_name": "",
    }
    result = await db["users"].insert_one(user)
    user["_id"] = str(result.inserted_id)
    return UserPublic(**user)

@router.post("/login")
async def login_user(request: LoginRequest):
    db = get_database()
    user = await db["users"].find_one({"email": request.email})
    if not user or not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access_token = create_access_token(
        data={"sub": user["email"], "role": user["role"]},
        expires_delta=timedelta(minutes=30)
    )
    return {"access_token": access_token, "token_type": "bearer"}