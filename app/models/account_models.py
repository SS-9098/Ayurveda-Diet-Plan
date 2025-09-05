from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Literal, Dict
from datetime import datetime


# --- Nested Profile Sub-Models ---
class BiologicalData(BaseModel):
    height_cm: int
    weight_kg: float
    age: int
    gender: Literal["male", "female"]
    activity_level: Literal["sedentary", "light", "moderate", "active", "very_active"]


class DailyNeeds(BaseModel):
    calories_kcal: int
    protein_g: int
    fat_g_avg: int
    carbohydrate_g_avg: int
    added_sugar_g_limit: int


class PatientProfile(BaseModel):
    assigned_doctor_id: str
    biological_data: Optional[BiologicalData] = None
    daily_needs: Optional[DailyNeeds] = None
    dietary_patterns: Literal["veg", "vegan", "non-veg"] = "non-veg"
    questionnaire_answers: Dict[str, int] = {}
    dosha_result: str
    allergies: List[str] = []
    approved_favor_ingredients: List[str] = []
    approved_avoid_ingredients: List[str] = []


class DoctorProfile(BaseModel):
    license_number: str
    issuing_council: str
    state_of_registration: str
    registration_date: datetime
    registration_validity_date: datetime
    aadhaar_number: str  # Storing as a dummy string for the hackathon


class PatientBioUpdate(BaseModel):
    biological_data: BiologicalData
    dietary_patterns: Optional[Literal["veg", "vegan", "non-veg"]] = "non-veg"


# --- Base Model for Account Info ---
class AccountBase(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    email: EmailStr


# --- Models for Creating New Accounts ---
class DoctorCreate(AccountBase):
    license_number: str
    issuing_council: str
    state_of_registration: str
    registration_date: datetime
    registration_validity_date: datetime
    aadhaar_number: str


class PatientCreate(AccountBase):
    dosha_result: str
    allergies: List[str] = []
    questionnaire_answers: Dict[str, int] = {}


# Model representing the document in the 'accounts' collection
class AccountInDB(AccountBase):
    id: str = Field(alias="_id")
    role: Literal["doctor", "patient"]
    created_at: datetime = Field(default_factory=datetime.utcnow)

    doctor_profile: Optional[DoctorProfile] = None
    patient_profile: Optional[PatientProfile] = None

    class Config:
        populate_by_name = True


# Public-facing model (used for API responses)
class AccountPublic(AccountInDB):
    pass


# --- Authentication Models ---

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    sub: str  # The Account's ID (_id)
    role: str