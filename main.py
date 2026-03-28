from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from flask import send_from_directory

app = Flask(__name__)
CORS(app)

# Constants
CO2_FACTOR = 0.82
DAYS_YEAR = 365

# Approx wattage catalog (matching frontend devices)
WATTAGE_MAP = {
    "Smart TV": 100,
    "Set-Top Box": 30,
    "Gaming Console": 150,
    "Desktop Monitor": 80,
    "Phone Charger": 5,
    "Old Refrigerator": 150,
    "Microwave": 1200,
    "Incandescent Bulb (60W)": 60
}

# -------------------------------
# HELPER FUNCTION
# -------------------------------
def calculate_device(device, rate):
    watt = WATTAGE_MAP.get(device["name"], 100)
    hours = device["active_hours_per_day"]
    standby = device["stays_on_standby"]

    active_kwh_day = (watt * hours) / 1000

    standby_hours = max(0, 24 - hours)
    phantom_kwh_day = (5 * standby_hours) / 1000 if standby else 0

    total_kwh_day = active_kwh_day + phantom_kwh_day

    yearly_kwh = total_kwh_day * DAYS_YEAR
    yearly_cost = yearly_kwh * rate
    yearly_co2 = yearly_kwh * CO2_FACTOR

    phantom_cost = phantom_kwh_day * DAYS_YEAR * rate

    return {
        "name": device["name"],
        "yearly_cost": round(yearly_cost, 2),
        "yearly_co2": round(yearly_co2, 2),
        "phantom_waste": round(phantom_cost, 2),
        "watt": watt,
        "hours": hours
    }

# -------------------------------
# AUDIT API
# -------------------------------
@app.route("/api/audit", methods=["POST"])
def audit():
    data = request.get_json()

    rate = data.get("rate_per_kwh", 8)
    devices = data.get("appliances", [])

    all_data = [calculate_device(d, rate) for d in devices]

    # Summary
    total_cost = sum(d["yearly_cost"] for d in all_data)
    total_co2 = sum(d["yearly_co2"] for d in all_data)

    # Top offenders
    top_offenders = sorted(all_data, key=lambda x: x["yearly_cost"], reverse=True)[:3]

    # Recommendations
    recommendations = []

    if top_offenders:
        top = top_offenders[0]
        saving = (top["watt"] / 1000) * DAYS_YEAR * rate
        recommendations.append({
            "message": f"Reduce {top['name']} usage by 1 hour/day → Save ₹{round(saving,0)}/year"
        })

    standby_devices = [d for d in all_data if d["phantom_waste"] > 0]

    if standby_devices:
        standby_loss = sum(d["phantom_waste"] for d in standby_devices)
        recommendations.append({
            "message": f"Turn off standby devices → Save ₹{round(standby_loss,0)}/year"
        })

    return jsonify({
        "summary": {
            "yearly_cost": round(total_cost, 2),
            "yearly_co2": round(total_co2, 2)
        },
        "all_data": all_data,
        "top_offenders": top_offenders,
        "recommendations": recommendations
    })

# -------------------------------
# SIMULATION API
# -------------------------------
@app.route("/api/simulate", methods=["POST"])
def simulate():
    rate = float(request.args.get("rate_per_kwh", 8))
    device = request.get_json()

    base = calculate_device(device, rate)

    # Reduce 1 hour scenario
    reduced_device = device.copy()
    reduced_device["active_hours_per_day"] = max(0, device["active_hours_per_day"] - 1)

    new = calculate_device(reduced_device, rate)

    savings_rs = base["yearly_cost"] - new["yearly_cost"]
    savings_co2 = base["yearly_co2"] - new["yearly_co2"]

    return jsonify({
        "scenario": f"Reducing {device['name']} by 1 hour/day",
        "savings_rs": round(savings_rs, 2),
        "savings_co2": round(savings_co2, 2)
    })

# -------------------------------
# ROOT
# -------------------------------
@app.route("/")
def serve_frontend():
    return send_from_directory(".", "index.html")

# -------------------------------
# RUN FOR RENDER
# -------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)