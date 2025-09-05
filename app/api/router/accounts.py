from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorCollection
from app.models.account_models import AccountPublic
from app.db.database import get_collection

router = APIRouter()

@router.get("/{account_id}", response_model=AccountPublic)
async def get_account_details(
    account_id: str,
    accounts_coll: AsyncIOMotorCollection = Depends(get_collection("accounts"))
):
    """
    Retrieves the full profile for any account (doctor or patient) by their ID.
    """
    account = await accounts_coll.find_one({"_id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account
