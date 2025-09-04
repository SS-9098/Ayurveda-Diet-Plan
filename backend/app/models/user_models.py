from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Literal, Dict
from datetime import datetime
from bson import ObjectId


# This helper class for ObjectId is perfect. Keep it.
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


# --- Nested Profile Sub-Models ---

class BiologicalData(BaseModel):
    height_cm: int
    weight_kg: float
    age: int
    gender: Literal["male", "female"]
    activity_level: Literal["sedentary", "light", "moderate", "active", "very_active"]


class PatientProfile(BaseModel):
    assigned_doctor_id: Optional[PyObjectId] = None
    biological_data: Optional[BiologicalData] = None
    questionnaire_answers: Optional[Dict[str, int]] = None
    dosha_result: Optional[str] = None
    allergies: List[str] = []
    approved_favor_ingredients: List[str] = []
    approved_avoid_ingredients: List[str] = []


class DoctorProfile(BaseModel):
    registration_number: str
    issuing_council: str
    state_of_registration: str
    registration_date: datetime
    registration_validity_date: datetime
    registration_status: Literal["Active", "Provisional", "Suspended", "Expired"]
    # We'll handle Aadhaar separately in the service layer for security


# --- Core Account Models ---

class AccountBase(BaseModel):
    email: EmailStr = Field(...)
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    role: Literal["doctor", "patient"]


class AccountCreate(AccountBase):
    password: str = Field(..., min_length=8)
    # Include profile data during creation if needed
    doctor_profile: Optional[DoctorProfile] = None
    patient_profile: Optional[PatientProfile] = None


# Model representing the document in the 'accounts' collection
class AccountInDB(AccountBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    doctor_profile: Optional[DoctorProfile] = None
    patient_profile: Optional[PatientProfile] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


# Public-facing model (omits sensitive data like password)
class AccountPublic(AccountBase):
    id: str = Field(alias="_id")
    doctor_profile: Optional[DoctorProfile] = None
    patient_profile: Optional[PatientProfile] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


# --- Authentication Models ---

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    sub: str  # The Account's ID (_id)
    role: str