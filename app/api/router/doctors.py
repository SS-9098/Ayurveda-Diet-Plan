from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import StreamingResponse
from app.models.account_models import DoctorCreate, PatientCreate, AccountInDB, AccountPublic, BiologicalData
from app.models.recipe_models import IngredientListResponse
from app.db.database import get_collection
from app.services import diet_service, report_service
from datetime import datetime
import secrets
import string

router = APIRouter()


@router.post("/register", response_model=AccountPublic, status_code=201)
async def register_doctor(doctor_data: DoctorCreate):
    """Registers a new doctor and returns their profile with a unique ID."""
    accounts_coll = get_collection("accounts")
    if await accounts_coll.find_one({"doctor_profile.license_number": doctor_data.license_number}):
        raise HTTPException(status_code=400, detail="Doctor with this license number already registered")

    doctor_id = f"DOC-{''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))}"

    new_doctor_doc = {
        "_id": doctor_id,
        "first_name": doctor_data.first_name, "last_name": doctor_data.last_name,
        "email": doctor_data.email, "role": "doctor", "created_at": datetime.utcnow(),
        "doctor_profile": {
            "license_number": doctor_data.license_number, "issuing_council": doctor_data.issuing_council,
            "state_of_registration": doctor_data.state_of_registration,
            "registration_date": doctor_data.registration_date,
            "registration_validity_date": doctor_data.registration_validity_date,
            "aadhaar_number": doctor_data.aadhaar_number,
            "registration_status": "Active"
        },
        "patient_profile": None
    }
    await accounts_coll.insert_one(new_doctor_doc)
    return new_doctor_doc


@router.get("/{doctor_id}", response_model=AccountPublic)
async def doctor_login(doctor_id: str):
    """Simplified login for a doctor by fetching their data using the ID."""
    doctor = await get_collection("accounts").find_one({"_id": doctor_id, "role": "doctor"})
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor ID not found")
    return doctor


@router.post("/{doctor_id}/patients/register", response_model=AccountPublic, status_code=201)
async def register_patient_under_doctor(doctor_id: str, patient_data: PatientCreate):
    """Registers a new patient under a specific doctor's care."""
    accounts_coll = get_collection("accounts")
    if not await accounts_coll.find_one({"_id": doctor_id, "role": "doctor"}):
        raise HTTPException(status_code=404, detail="Doctor not found")

    patient_id = f"PATIENT-{''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))}"

    new_patient_doc = {
        "_id": patient_id, "first_name": patient_data.first_name, "last_name": patient_data.last_name,
        "email": patient_data.email, "role": "patient", "created_at": datetime.utcnow(),
        "doctor_profile": None,
        "patient_profile": {
            "assigned_doctor_id": doctor_id, "dosha_result": patient_data.dosha_result,
            "allergies": patient_data.allergies, "questionnaire_answers": patient_data.questionnaire_answers,
            "approved_favor_ingredients": [], "approved_avoid_ingredients": [],
        }
    }
    await accounts_coll.insert_one(new_patient_doc)
    return new_patient_doc


@router.post("/patients/{patient_id}/generate-ingredient-list", response_model=IngredientListResponse)
async def generate_ingredient_list_for_patient(patient_id: str):
    """Generates the initial ingredient chart based on a patient's profile."""
    patient = await get_collection("accounts").find_one({"_id": patient_id, "role": "patient"})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    profile = patient.get('patient_profile', {})
    return diet_service.generate_ingredient_list(profile.get('dosha_result', ''), profile.get('allergies', []))


@router.get("/patients/{patient_id}/ingredient-chart/pdf")
async def download_ingredient_chart_pdf(patient_id: str):
    """Generates and provides a downloadable PDF of the ingredient chart."""
    chart_data = await generate_ingredient_list_for_patient(patient_id)
    pdf_buffer = report_service.create_ingredient_pdf(chart_data['favor_ingredients'], chart_data['avoid_ingredients'])
    return StreamingResponse(pdf_buffer, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={patient_id}_ingredient_chart.pdf"})


@router.post("/patients/{patient_id}/update-bio", response_model=AccountPublic)
async def update_patient_bio(patient_id: str, bio_data: BiologicalData):
    """
    Updates the biological data for a patient. This is a prerequisite for generating a recipe plan.
    """
    accounts_coll = get_collection("accounts")
    
    # Find the patient
    patient = await accounts_coll.find_one({"_id": patient_id, "role": "patient"})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Update the biological data
    result = await accounts_coll.update_one(
        {"_id": patient_id},
        {"$set": {"patient_profile.biological_data": bio_data.dict()}}
    )

    if result.modified_count == 0:
        # This might happen if the data is the same, but we can also treat it as an indicator that something is off.
        # For the purpose of the hackathon, we can assume this is fine.
        pass

    # Return the updated patient document
    updated_patient = await accounts_coll.find_one({"_id": patient_id})
    return updated_patient


@router.post("/patients/{patient_id}/recipe-plan/pdf")
async def generate_recipe_plan_pdf(patient_id: str):
    """Generates a 7-day recipe plan PDF based on patient's biological data."""
    patient = await get_collection("accounts").find_one({"_id": patient_id, "role": "patient"})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient_profile = patient.get('patient_profile', {})
    
    if not patient_profile.get('biological_data'):
        raise HTTPException(status_code=400, detail="Biological data must be set for the patient before generating a recipe plan.")

    # For the MVP, we assume the initially generated list is the "approved" list.
    initial_list = diet_service.generate_ingredient_list(patient_profile.get('dosha_result', ''),
                                                         patient_profile.get('allergies', []))
    patient_profile['approved_favor_ingredients'] = initial_list['favor_ingredients']
    patient_profile['approved_avoid_ingredients'] = initial_list['avoid_ingredients']

    recipe_plan = diet_service.generate_recipe_plan(patient_profile)

    if "error" in recipe_plan:
        raise HTTPException(status_code=400, detail=recipe_plan["error"])

    pdf_buffer = report_service.create_recipe_plan_pdf(recipe_plan)
    return StreamingResponse(pdf_buffer, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={patient_id}_recipe_plan.pdf"})

