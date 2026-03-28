from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import os

app = FastAPI(title="Phantom Load Auditor API")

# 1. THE DATA SET
APPLIANCE_CATALOG = {
    "Smart TV": {"active_w": 100, "standby_w": 10},
    "Set-Top Box": {"active_w": 25, "standby_w": 15},
    "Gaming Console": {"active_w": 150, "standby_w": 15},
    "Desktop Monitor": {"active_w": 40, "standby_w": 5},
    "Phone Charger": {"active_w": 15, "standby_w": 1},
    "Old Refrigerator": {"active_w": 400, "standby_w": 0},
    "Microwave": {"active_w": 800, "standby_w": 3},
    "Incandescent Bulb (60W)": {"active_w": 60, "standby_w": 0}
}

SWAP_DB = {
    "Incandescent Bulb (60W)": {"suggestion": "9W LED", "new_active_w": 9, "new_standby_w": 0},
    "Old Refrigerator": {"suggestion": "5-Star Inverter Fridge", "new_active_w": 150, "new_standby_w": 0},
    "Smart TV": {"suggestion": "Disable 'Fast-Start' setting", "new_active_w": 100, "new_standby_w": 0}
}

CO2_PER_KWH = 0.82 

# 2. DATA MODELS
class UserAppliance(BaseModel):
    id: str
    room: str
    name: str
    is_custom: bool
    custom_active_w: Optional[float] = 0
    custom_standby_w: Optional[float] = 0
    active_hours_per_day: float
    stays_on_standby: bool

class AuditRequest(BaseModel):
    rate_per_kwh: float
    appliances: List[UserAppliance]

# 3. ENDPOINTS
@app.post("/api/audit")
def calculate_audit(req: AuditRequest):
    results = []
    totals = {"yearly_cost": 0, "yearly_co2": 0}
    recommendations = []

    for item in req.appliances:
        if item.name not in APPLIANCE_CATALOG:
            continue
            
        specs = APPLIANCE_CATALOG[item.name]
        act_w = specs["active_w"]
        stb_w = specs["standby_w"]

        standby_hours = max(0, 24 - item.active_hours_per_day) if item.stays_on_standby else 0
        daily_kwh = ((act_w * item.active_hours_per_day) + (stb_w * standby_hours)) / 1000
        yearly_kwh = daily_kwh * 365
        
        yearly_cost = yearly_kwh * req.rate_per_kwh
        yearly_co2 = yearly_kwh * CO2_PER_KWH
        phantom_waste_cost = ((stb_w * standby_hours) / 1000) * 365 * req.rate_per_kwh

        waste_score = yearly_cost + (yearly_co2 * 0.5) + (phantom_waste_cost * 2)

        results.append({
            "id": item.id,
            "room": item.room,
            "name": item.name,
            "yearly_cost": round(yearly_cost, 2),
            "phantom_waste": round(phantom_waste_cost, 2),
            "waste_score": round(waste_score, 2)
        })

        totals["yearly_cost"] += yearly_cost
        totals["yearly_co2"] += yearly_co2

        if item.name in SWAP_DB:
            swap = SWAP_DB[item.name]
            new_kwh = ((swap["new_active_w"] * item.active_hours_per_day) + (swap["new_standby_w"] * standby_hours)) / 1000
            new_cost = (new_kwh * 365) * req.rate_per_kwh
            new_co2 = (new_kwh * 365) * CO2_PER_KWH
            
            savings_rs = yearly_cost - new_cost
            savings_co2 = yearly_co2 - new_co2
            
            if savings_rs > 0:
                recommendations.append({
                    "appliance": item.name,
                    "room": item.room,
                    "message": f"Swap to {swap['suggestion']} to save ₹{int(savings_rs)}/yr and {int(savings_co2)} kg CO₂."
                })

    results.sort(key=lambda x: x["waste_score"], reverse=True)

    return {
        "summary": {k: round(v, 2) for k, v in totals.items()},
        "top_offenders": results[:3],
        "recommendations": recommendations,
        "all_data": results
    }

@app.post("/api/simulate")
def run_what_if(req: UserAppliance, rate_per_kwh: float):
    act_w = APPLIANCE_CATALOG.get(req.name, {}).get("active_w", 0)
    stb_w = APPLIANCE_CATALOG.get(req.name, {}).get("standby_w", 0)
    
    current_kwh = ((act_w * req.active_hours_per_day) + (stb_w * (24 - req.active_hours_per_day))) / 1000
    current_cost = current_kwh * 365 * rate_per_kwh

    sim_kwh = ((act_w * req.active_hours_per_day) + 0) / 1000
    sim_cost = sim_kwh * 365 * rate_per_kwh
    
    saved_money = current_cost - sim_cost
    saved_co2 = (current_kwh - sim_kwh) * 365 * CO2_PER_KWH

    return {
        "scenario": f"Unplugging your {req.name} when not in use.",
        "savings_rs": round(saved_money, 2),
        "savings_co2": round(saved_co2, 2)
    }

# --- THE FIX ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.get("/")
async def read_index():
    index_path = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    # If the file is missing, this tells you why in the browser
    raise HTTPException(status_code=404, detail=f"index.html not found. Check root directory.")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)