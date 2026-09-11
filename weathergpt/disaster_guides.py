"""
disaster_guides.py - Disaster Preparedness Protocols & Offline Emergency Knowledge Base
Aligned with NDMA (National Disaster Management Authority) & IMD (India Meteorological Department) guidelines.
"""

DISASTER_PROTOCOLS = {
    "flood": {
        "title": "Urban Flood & Flash Flood Safety Protocol",
        "imd_code": "RED",
        "immediate_actions": [
            "Move immediately to higher ground or upper floors of sturdy concrete buildings.",
            "Do NOT attempt to walk, swim, or drive through moving flood waters (just 15 cm of moving water can knock you down, and 30 cm can float a vehicle).",
            "Turn off the main electrical circuit breaker and gas cylinder valves before evacuating.",
            "Avoid contact with downed power lines or electrical wires submerged in water.",
            "Boil all drinking water or use water purification tablets to prevent water-borne infections (cholera, leptospirosis)."
        ],
        "emergency_kit": [
            "Waterproof pouch with ID, insurance, property records, cash",
            "3 days of bottled water (3 liters/person/day) and dry ready-to-eat rations",
            "Battery-operated transistor radio, LED torch, spare batteries",
            "First aid kit, antiseptic liquid, ORS packets, essential chronic medications",
            "High-decibel whistle to signal rescue teams",
            "Sturdy boots and high-visibility rain poncho"
        ],
        "emergency_helpline": "1078 (National Disaster Management Authority) / 112 (National Emergency)"
    },
    "heatwave": {
        "title": "Severe Heatwave & Sunstroke Safety Protocol",
        "imd_code": "ORANGE",
        "immediate_actions": [
            "Avoid direct sun exposure between 11:00 AM and 4:00 PM.",
            "Drink plenty of water even if you do not feel thirsty; consume ORS, lassi, torani (rice water), coconut water, and lemon water.",
            "Wear lightweight, light-colored, loose, and porous cotton clothes.",
            "Never leave children, elderly, or pets in a closed, parked vehicle.",
            "If someone experiences dizziness, rapid pulse, or ceases sweating with high fever, move them to shade, apply wet cloths to neck and armpits, and call medical help immediately."
        ],
        "emergency_kit": [
            "ORS (Oral Rehydration Salts) and electrolyte packets",
            "Wide-brimmed hat, UV400 sunglasses, umbrella",
            "Reusable insulated stainless-steel water bottle",
            "Cooling wet wipes or micro-fiber cooling towels",
            "Sunscreen (SPF 50+ broad spectrum)"
        ],
        "emergency_helpline": "108 (Ambulance) / 1070 (State Emergency Operations Center)"
    },
    "cyclone": {
        "title": "Cyclone & Severe Gale Wind Protocol",
        "imd_code": "RED",
        "immediate_actions": [
            "Inspect roof and secure loose tiles, tin sheets, or rooftop structures.",
            "Board up glass windows or paste heavy-duty tape diagonally to reduce shatter hazard.",
            "Clear outdoor areas of loose objects, branches, or signage that could turn into high-velocity projectiles.",
            "Keep mobile phones, power banks, and emergency lanterns fully charged.",
            "Do NOT go outside during the lull ('eye of the cyclone') as destructive winds will reverse violently without warning."
        ],
        "emergency_kit": [
            "Fully charged 20,000 mAh power bank and extra charging cables",
            "Emergency radio tuned to All India Radio / IMD broadcasts",
            "Waterproof emergency documents pouch",
            "Non-perishable canned food, biscuits, dry fruits",
            "Duct tape, nylon rope, Swiss knife or multi-tool"
        ],
        "emergency_helpline": "1077 (District Emergency Relief) / 1078 (NDMA)"
    },
    "air_pollution": {
        "title": "Hazardous Air Quality & Smog Emergency Protocol",
        "imd_code": "RED",
        "immediate_actions": [
            "Strictly avoid outdoor jogging, vigorous physical exercise, or prolonged walking when AQI exceeds 200.",
            "Wear a certified N95 or N99 particulate respirator mask whenever outdoor transit is unavoidable.",
            "Keep doors and windows sealed; use HEPA air purifiers indoors if accessible.",
            "Avoid burning candles, incense, mosquito coils, or biomass indoors.",
            "Vulnerable groups (asthmatic, COPD, elderly, young children) should keep rescue inhalers within arm's reach."
        ],
        "emergency_kit": [
            "Certified N95 / N99 anti-pollution masks",
            "Saline nasal spray and lubricating eye drops",
            "Prescribed inhalers and pulse oximeter",
            "Indoor air quality monitoring device or app bookmark"
        ],
        "emergency_helpline": "112 (Emergency Medical Assistance) / CPCB Portal"
    },
    "thunderstorm": {
        "title": "Severe Thunderstorm & Lightning Safety Protocol",
        "imd_code": "YELLOW",
        "immediate_actions": [
            "Follow the 30-30 Rule: If the time between lightning and thunder is under 30 seconds, seek indoor shelter immediately; stay indoors 30 minutes after the last thunderclap.",
            "Avoid standing under tall, isolated trees, open sheds, or near metal fences and towers.",
            "If trapped in open fields, crouch low on the balls of your feet with hands on knees; do NOT lie flat on the ground.",
            "Unplug sensitive household electronics, computers, and television sets to prevent power surge damage.",
            "Do NOT use plumbing or take showers during an electrical storm as lightning can travel through copper pipes."
        ],
        "emergency_kit": [
            "Surge protectors on essential appliances",
            "Rechargeable emergency lanterns",
            "Battery-powered communication devices"
        ],
        "emergency_helpline": "112 / Damini App (Lightning Alert by Ministry of Earth Sciences)"
    }
}


def get_protocol_for_hazard(event_type: str) -> dict:
    """Returns the matching disaster protocol or general preparedness."""
    event_lower = event_type.lower()
    for key, protocol in DISASTER_PROTOCOLS.items():
        if key in event_lower:
            return protocol
    if "rain" in event_lower or "water" in event_lower or "deluge" in event_lower:
        return DISASTER_PROTOCOLS["flood"]
    if "heat" in event_lower or "temperature" in event_lower or "warm" in event_lower:
        return DISASTER_PROTOCOLS["heatwave"]
    if "wind" in event_lower or "storm" in event_lower or "gale" in event_lower:
        return DISASTER_PROTOCOLS["cyclone"]
    if "aqi" in event_lower or "air" in event_lower or "smog" in event_lower or "pollution" in event_lower:
        return DISASTER_PROTOCOLS["air_pollution"]
    return DISASTER_PROTOCOLS["thunderstorm"]
