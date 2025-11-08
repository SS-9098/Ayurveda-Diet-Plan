from fastapi import APIRouter, HTTPException, Body, Depends
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorCollection
from app.models.account_models import DoctorCreate, PatientCreate, AccountPublic, BiologicalData, PatientBioUpdate, LoginRequest
from app.models.recipe_models import IngredientListResponse
from app.db.database import get_collection
from app.services import diet_service, report_service
from datetime import datetime
from uuid import uuid4
import string
from typing import Dict

router = APIRouter()


@router.post("/register", response_model=AccountPublic, status_code=201)
async def register_doctor(
    doctor_data: DoctorCreate,
    accounts_coll: AsyncIOMotorCollection = Depends(get_collection("accounts"))
):
    """Registers a new doctor and returns their profile with a unique ID."""
    if await accounts_coll.find_one({"email": doctor_data.email}):
        raise HTTPException(status_code=400, detail="Doctor with this email already registered")

    doctor_id = f"DOC-{''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))}"
    new_doctor_doc = {
        "_id": doctor_id,
        "first_name": doctor_data.first_name, "last_name": doctor_data.last_name,
        "email": doctor_data.email, "role": "doctor", "created_at": datetime.utcnow(),
        "password": doctor_data.password,  # Storing plain text password as requested
        "doctor_profile": {
            "license_number": doctor_data.license_number, "issuing_council": doctor_data.issuing_council,
            "state_of_registration": doctor_data.state_of_registration,
            "registration_date": doctor_data.registration_date,
            "registration_validity_date": doctor_data.registration_validity_date,
            "registration_status": "Active"
        },
        "patient_profile": None
    }
    await accounts_coll.insert_one(new_doctor_doc)
    # Fetch the document back to ensure it matches the response model
    created_doctor = await accounts_coll.find_one({"_id": doctor_id})
    return {"id":created_doctor.get("_id")}


@router.post("/login", response_model=Dict[str, str])
async def doctor_login(
    login_data: LoginRequest,
    accounts_coll: AsyncIOMotorCollection = Depends(get_collection("accounts"))
):
    """Authenticates a doctor and returns their ID and role."""
    doctor = await accounts_coll.find_one({"email": login_data.email, "role": "doctor"})
    if not doctor or doctor.get("password")!= login_data.password:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return {"id": doctor["_id"], "role": doctor["role"]}


@router.post("/{doctor_id}/patients/register", response_model=AccountPublic, status_code=201)
async def register_patient_under_doctor(
    doctor_id: str,
    patient_data: PatientCreate,
    accounts_coll: AsyncIOMotorCollection = Depends(get_collection("accounts"))
):
    """Registers a new patient under a specific doctor's care."""
    if not await accounts_coll.find_one({"_id": doctor_id, "role": "doctor"}):
        raise HTTPException(status_code=404, detail="Doctor not found")
    
    if await accounts_coll.find_one({"email": patient_data.email}):
        raise HTTPException(status_code=400, detail="Patient with this email already exists")

    patient_id = f"PATIENT-{uuid4().hex[:8].upper()}"

    new_patient_doc = {
        "_id": patient_id,
        "first_name": patient_data.first_name,
        "last_name": patient_data.last_name,
        "email": patient_data.email,
        "role": "patient",
        "created_at": datetime.utcnow(),
        "password": patient_data.first_name,  # Default password is the first name
        "doctor_profile": None,
        "patient_profile": {
            "assigned_doctor_id": doctor_id,
            "dosha_result": patient_data.dosha_result,
            "allergies": patient_data.allergies,
            "questionnaire_answers": patient_data.questionnaire_answers,
            "approved_favor_ingredients": [],
            "approved_avoid_ingredients": [],
        },
    }
    await accounts_coll.insert_one(new_patient_doc)
    created_patient = await accounts_coll.find_one({"_id": patient_id})
    return created_patient


@router.post("/patients/{patient_id}/generate-ingredient-list", response_model=IngredientListResponse)
async def generate_ingredient_list_for_patient(
    patient_id: str,
    accounts_coll: AsyncIOMotorCollection = Depends(get_collection("accounts"))
):
    """Generates the initial ingredient chart based on a patient's profile."""
    patient = await accounts_coll.find_one({"_id": patient_id, "role": "patient"})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    profile = patient.get('patient_profile', {})
    return diet_service.generate_ingredient_list(profile.get('dosha_result', ''), profile.get('allergies', []))


@router.get("/patients/{patient_id}/ingredient-chart/pdf")
async def download_ingredient_chart_pdf(
    patient_id: str,
    accounts_coll: AsyncIOMotorCollection = Depends(get_collection("accounts"))
):
    """Generates and provides a downloadable PDF of the ingredient chart."""
    patient = await accounts_coll.find_one({"_id": patient_id, "role": "patient"})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    profile = patient.get('patient_profile', {})
    chart_data = diet_service.generate_ingredient_list(profile.get('dosha_result', ''), profile.get('allergies', []))

    pdf_buffer = report_service.create_ingredient_pdf(chart_data['favor_ingredients'], chart_data['avoid_ingredients'])
    return StreamingResponse(pdf_buffer, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={patient_id}_ingredient_chart.pdf"})


@router.post("/patients/{patient_id}/update-bio", response_model=AccountPublic)
async def update_patient_bio(
    patient_id: str,
    update_data: PatientBioUpdate,
    accounts_coll: AsyncIOMotorCollection = Depends(get_collection("accounts"))
):
    """
    Updates the biological and dietary data for a patient. This also recalculates their daily nutritional needs.
    """
    patient = await accounts_coll.find_one({"_id": patient_id, "role": "patient"})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Calculate daily needs based on the new biological data
    daily_needs = diet_service.calculate_daily_needs(update_data.biological_data)

    # Prepare the update document
    update_fields = {
        "patient_profile.biological_data": update_data.biological_data.dict(),
        "patient_profile.dietary_patterns": update_data.dietary_patterns,
        "patient_profile.daily_needs": daily_needs
    }

    await accounts_coll.update_one(
        {"_id": patient_id},
        {"$set": update_fields}
    )

    updated_patient = await accounts_coll.find_one({"_id": patient_id})
    return updated_patient


@router.post("/patients/{patient_id}/recipe-plan/pdf")
async def generate_recipe_plan_pdf(
    patient_id: str,
    accounts_coll: AsyncIOMotorCollection = Depends(get_collection("accounts"))
):
    """Generates a 7-day recipe plan PDF based on patient's biological data."""
    patient = await accounts_coll.find_one({"_id": patient_id, "role": "patient"})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient_profile = patient.get('patient_profile', {})

    if not patient_profile.get('biological_data'):
        raise HTTPException(status_code=400, detail="Biological data must be set for the patient before generating a recipe plan.")

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