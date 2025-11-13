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
from app.models.recipe_models import DayMeals,FinalDayMeals
import secrets
import logging
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

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
    """Generates the initial ingredient chart based on a patient's profile and saves the approved lists to the patient document."""
    patient = await accounts_coll.find_one({"_id": patient_id, "role": "patient"})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    profile = patient.get('patient_profile') or {}

    chart_data = diet_service.generate_ingredient_list(profile.get('dosha_result', ''), profile.get('allergies', []))

    # Merge into existing profile (or create a new one) and persist the approved lists safely
    updated_profile = {**profile}
    updated_profile['approved_favor_ingredients'] = chart_data['favor_ingredients']
    updated_profile['approved_avoid_ingredients'] = chart_data['avoid_ingredients']

    await accounts_coll.update_one(
        {"_id": patient_id},
        {"$set": {"patient_profile": updated_profile}}
    )

    return chart_data


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


@router.post("/patients/{patient_id}/create-recipe-plan", response_model=Dict[str, DayMeals])
async def create_recipe_plan(
    patient_id: str,
    accounts_coll: AsyncIOMotorCollection = Depends(get_collection("accounts"))
):
    """
    Generates a new recipe plan with alternatives for the patient.
    Returns a mapping of day keys (e.g. "1") to DayMeals (breakfast/lunch/snacks/dinner).
    """
    projection = {
        "patient_profile.biological_data": 1,
        "patient_profile.daily_needs": 1,
        "patient_profile.dosha_result": 1,
        "patient_profile.allergies": 1,
        "patient_profile.dietary_patterns": 1
    }
    patient = await accounts_coll.find_one({"_id": patient_id, "role": "patient"}, projection)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient_profile = patient.get("patient_profile", {})
    if not patient_profile.get("biological_data"):
        raise HTTPException(status_code=400, detail="Biological data must be set before generating a recipe plan.")

    recipe_options = diet_service.generate_recipe_plan_options(patient_profile)
    if "error" in recipe_options:
        raise HTTPException(status_code=400, detail=recipe_options["error"])

    return recipe_options


@router.post("/patients/{patient_id}/finalize-recipe-plan")
async def finalize_recipe_plan(
    patient_id: str,
    finalized_plan: Dict[str, FinalDayMeals] = Body(...),
    accounts_coll: AsyncIOMotorCollection = Depends(get_collection("accounts"))
):
    """
    Saves the user-finalized recipe plan (validated as Dict[str, DayMeals]) to the database.
    """
    patient = await accounts_coll.find_one({"_id": patient_id, "role": "patient"})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Convert validated Pydantic models to dicts for MongoDB storage
    store_plan = {day: meals.dict() for day, meals in finalized_plan.items()}

    await accounts_coll.update_one(
        {"_id": patient_id},
        {"$set": {"patient_profile.finalized_recipe_plan": store_plan}}
    )
    return {"message": "Recipe plan finalized and saved successfully."}


@router.post("/patients/{patient_id}/recipe-plan/pdf")
async def generate_recipe_plan_pdf(
    patient_id: str,
    accounts_coll: AsyncIOMotorCollection = Depends(get_collection("accounts"))
):
    """
    Generates a PDF for the patient's FINALIZED recipe plan.
    This endpoint fetches the finalized plan from the database and formats it for PDF output.
    """
    projection = {
        "patient_profile.finalized_recipe_plan": 1,
        "patient_profile.daily_needs": 1
    }
    patient = await accounts_coll.find_one({"_id": patient_id, "role": "patient"}, projection)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient_profile = patient.get("patient_profile", {})
    finalized_plan = patient_profile.get("finalized_recipe_plan")
    daily_needs = patient_profile.get("daily_needs")

    if not finalized_plan:
        raise HTTPException(status_code=400, detail="No finalized recipe plan found for this patient.")
    if not daily_needs:
        raise HTTPException(status_code=400, detail="Daily needs are not set for this patient.")

    # Format the plan for the PDF service
    formatted_plan = diet_service.format_finalized_plan_for_pdf(finalized_plan, daily_needs)

    if "error" in formatted_plan:
        raise HTTPException(status_code=400, detail=formatted_plan["error"])

    pdf_buffer = report_service.create_recipe_plan_pdf(formatted_plan)
    return StreamingResponse(pdf_buffer, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={patient_id}_recipe_plan.pdf"})