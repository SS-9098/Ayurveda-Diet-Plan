import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any
import httpx

# Import the generate_meal_plan function from OR_Model.py
from OR_Model import generate_meal_plan

app = FastAPI()

# Define a Pydantic model for the user profile
class UserProfile(BaseModel):
    cal: 2000
    prot: 75
    fat: 60
    sugar: 30
    dosha: "Vata"
    nuts: False
    diary: False
    veg: False
    vegan: False

@app.get("/generate-meal-plan")
def generate_meal_plan_endpoint(user_profile_url: str):
    try:
        # Fetch the user profile from the external API
        with httpx.Client() as client:
            response = client.get(user_profile_url)
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch user profile.")
            user_profile_dict = response.json()

        # Validate the user profile
        user_profile_obj = UserProfile(**user_profile_dict)

        # Call the generate_meal_plan function
        csv_file = "food_recipies.csv"
        result = generate_meal_plan(csv_file, user_profile=user_profile_obj.dict())

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return result
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Error connecting to user profile API: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)