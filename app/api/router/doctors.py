from fastapi import APIRouter, HTTPException
from app.models.account_models import DoctorProfile, PatientCreate, AccountInDB
from app.db.database import get_collection
import secrets
import string

router = APIRouter()


@router.post("/register", response_model=AccountInDB)
async def register_doctor(doctor: DoctorProfile):
    accounts_coll = get_collection("accounts")
    # For hackathon, we assume license is unique
    if await accounts_coll.find_one({"doctor_profile.license_number": doctor.license_number}):
        raise HTTPException(status_code=400, detail="Doctor with this license number already exists")

    new_doctor = {
        "_id": ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(10)),
        "first_name": doctor.first_name,
        "last_name": doctor.last_name,
        "role": "doctor",
        "doctor_profile": {"license_number": doctor.license_number}
    }
    await accounts_coll.insert_one(new_doctor)
    return new_doctor


@router.post("/{doctor_id}/patients/register", response_model=AccountInDB)
async def register_patient(doctor_id: str, patient: PatientCreate):
    accounts_coll = get_collection("accounts")
    # Check if doctor exists
    doctor = await accounts_coll.find_one({"_id": doctor_id, "role": "doctor"})
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    patient_id = f"PATIENT-{''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))}"

    new_patient = {
        "_id": patient_id,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "role": "patient",
        "patient_profile": {
            "assigned_doctor_id": doctor_id,
            "dosha_result": patient.dosha_result,
            "allergies": patient.allergies
        }
    }
    await accounts_coll.insert_one(new_patient)
    return new_patient
