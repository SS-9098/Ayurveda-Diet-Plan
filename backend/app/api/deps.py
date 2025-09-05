from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from backend.app.core.security import decode_access_token
from backend.app.models.user_models import TokenPayload
from backend.db_mongo import get_database

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_user(email: str):
    db = get_database()
    user = await db["users"].find_one({"email": email})
    return user

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise credentials_exception
    email = payload.get("sub")
    token_data = TokenPayload(sub=email, role=payload.get("role"))
    user = await get_user(email=token_data.sub)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: dict = Depends(get_current_user)):
    return current_user

async def doctor_only(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can access this endpoint"
        )
    return current_user

async def patient_only(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patients can access this endpoint"
        )
    return current_user

async def doctor_or_self(current_user: dict = Depends(get_current_user), patient_id: str = None):
    if current_user["role"] == "doctor" or (patient_id and str(current_user["_id"]) == patient_id):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have permission to access this resource"
    )