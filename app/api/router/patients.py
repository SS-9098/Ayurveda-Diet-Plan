from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorCollection
from app.models.account_models import AccountPublic, LoginRequest
from app.db.database import get_collection
from typing import Dict, Any

router = APIRouter()


@router.post("/login", response_model=Dict[str, str])
async def patient_login(
    login_data: LoginRequest,
    accounts_coll: AsyncIOMotorCollection = Depends(get_collection("accounts"))
):
    """Authenticates a patient and returns their ID and role."""
    patient = await accounts_coll.find_one({"email": login_data.email, "role": "patient"})
    if not patient or patient["password"] != login_data.password:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return {"_id": patient["_id"], "role": patient["role"]}


@router.get("/{patient_id}/bio-needs", response_model=Dict[str, Any])
async def get_bio_needs(
    patient_id: str,
    accounts_coll: AsyncIOMotorCollection = Depends(get_collection("accounts"))
):
    """
    Retrieves a simplified summary of the patient's biological and dietary needs.
    """
    patient = await accounts_coll.find_one({"_id": patient_id, "role": "patient"})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    profile = patient.get("patient_profile", {})
    needs = profile.get("daily_needs", {})
    allergies = profile.get("allergies", [])
    dietary_patterns = profile.get("dietary_patterns", "non-veg")

    return {
        "cal": needs.get("calories_kcal"),
        "prot": needs.get("protein_g"),
        "fat": needs.get("fat_g_avg"),
        "sugar": needs.get("added_sugar_g_limit"),
        "dosha": profile.get("dosha_result"),
        "nuts": "nuts" in allergies,
        "dairy": "dairy" in allergies,
        "veg": dietary_patterns == "veg",
        "vegan": dietary_patterns == "vegan",
    }