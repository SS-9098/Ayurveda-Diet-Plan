from fastapi import APIRouter, HTTPException
from app.models.account_models import AccountPublic
from app.db.database import get_collection

router = APIRouter()


@router.get("/{patient_id}", response_model=AccountPublic)
async def patient_login(patient_id: str):
    """Simplified login for a patient by fetching their data using the ID."""
    patient = await get_collection("accounts").find_one({"_id": patient_id, "role": "patient"})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient ID not found")
    return patient
