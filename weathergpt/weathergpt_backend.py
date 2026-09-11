# weathergpt_backend.py
"""
WeatherGPT Backend: Intelligent Conversational AI for Weather, Alerts,
Climate Analytics, and Disaster Safety (SIH26068 - Team Cryptic).
"""

import os
import json
import time
import requests
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Depends, HTTPException, Query, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response

from pydantic import BaseModel, Field

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Boolean,
    Text
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# SpaCy NLP
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except Exception:
    nlp = None

# OpenAI Client
from openai import OpenAI

from disaster_guides import DISASTER_PROTOCOLS, get_protocol_for_hazard


# ============================================================
# CONFIGURATION
# ============================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./weathergpt.db")

WEATHER_API = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_API = "https://air-quality-api.open-meteo.com/v1/air-quality"
ARCHIVE_API = "https://archive-api.open-meteo.com/v1/archive"
GEOCODE_API = "https://geocoding-api.open-meteo.com/v1/search"

# In-Memory Telemetry Cache (5 min TTL)
_TELEMETRY_CACHE: Dict[tuple, tuple] = {}
CACHE_TTL = 300

# Geocode Cache
_GEOCODE_CACHE: Dict[str, list] = {}


def get_openai_client(custom_key: Optional[str] = None) -> Optional[OpenAI]:
    key = custom_key.strip() if custom_key and custom_key.strip() else OPENAI_API_KEY
    if key:
        return OpenAI(api_key=key)
    return None


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="WeatherGPT Conversational Intelligence Platform",
    description="Conversational AI for Weather, Predictive Hazards, Climate Analytics, and NDMA Disaster Safety (SIH26068)",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# DATABASE SETUP
# ============================================================

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, nullable=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    city_name = Column(String, nullable=True)
    alert_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AlertHistory(Base):
    __tablename__ = "alert_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    location_name = Column(String, nullable=True)
    event = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    imd_color = Column(String, default="YELLOW")
    description = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    delivered = Column(Boolean, default=False)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================
# PYDANTIC SCHEMAS
# ============================================================

class ChatMessage(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    message: str = Field(..., min_length=1)
    latitude: float = Field(default=28.6139, ge=-90, le=90)
    longitude: float = Field(default=77.2090, ge=-180, le=180)
    city_name: Optional[str] = "New Delhi"
    session_id: Optional[str] = "default"
    history: List[ChatMessage] = []
    api_key: Optional[str] = None


class SimulateAlertRequest(BaseModel):
    scenario: str
    city_name: str = "Test Zone"
    latitude: float = 28.6139
    longitude: float = 77.2090


# ============================================================
# CONVERSATION SESSION STATE
# ============================================================

class ConversationSession:
    def __init__(self, session_id: str, city: str = "New Delhi", lat: float = 28.6139, lon: float = 77.2090):
        self.session_id = session_id
        self.city_name = city
        self.latitude = lat
        self.longitude = lon
        self.referenced_date = "today"    # "today", "tomorrow", "weekend", "YYYY-MM-DD"
        self.referenced_time = None       # "morning", "afternoon", "evening", "night", "6"
        self.last_activity = None         # "running", "biking", "commuting", "swimming"
        self.last_intent = None
        self.last_weather = None
        self.updated_at = time.time()

    def update_location(self, city: str, lat: float, lon: float):
        self.city_name = city
        self.latitude = lat
        self.longitude = lon
        self.referenced_date = "today"
        self.referenced_time = None
        self.updated_at = time.time()


_SESSION_STORE: Dict[str, ConversationSession] = {}


def get_or_create_session(session_id: str, city: str, lat: float, lon: float) -> ConversationSession:
    sid = session_id or "default"
    if sid not in _SESSION_STORE:
        _SESSION_STORE[sid] = ConversationSession(sid, city, lat, lon)
    return _SESSION_STORE[sid]


# ============================================================
# WEATHER DATA FETCHERS (Fast & Parallel)
# ============================================================

WMO_CODE_MAP = {
    0: ("Clear Sky", "clear skies"),
    1: ("Mainly Clear", "mostly sunny skies"),
    2: ("Partly Cloudy", "partly cloudy skies"),
    3: ("Overcast", "overcast skies"),
    45: ("Foggy", "foggy conditions"),
    48: ("Foggy", "dense fog"),
    51: ("Light Drizzle", "light drizzle"),
    53: ("Drizzle", "drizzle"),
    55: ("Dense Drizzle", "heavy drizzle"),
    61: ("Light Rain", "light rain"),
    63: ("Moderate Rain", "steady rain"),
    65: ("Heavy Rain", "heavy rain"),
    71: ("Light Snow", "light snow"),
    73: ("Snowfall", "snow"),
    75: ("Heavy Snow", "heavy snow"),
    80: ("Rain Showers", "passing showers"),
    81: ("Moderate Showers", "showers"),
    82: ("Violent Showers", "torrential cloudburst showers"),
    95: ("Thunderstorm", "thunderstorms"),
    96: ("Thunderstorm with Hail", "thunderstorms with hail"),
    99: ("Severe Storm", "heavy thunderstorm with hail")
}


def get_live_weather(latitude: float, longitude: float) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m,surface_pressure,uv_index",
        "hourly": "temperature_2m,precipitation_probability,precipitation,wind_speed_10m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,uv_index_max,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,weather_code",
        "forecast_days": 7,
        "timezone": "auto"
    }
    resp = requests.get(WEATHER_API, params=params, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    code = data.get("current", {}).get("weather_code", 0)
    cond, desc = WMO_CODE_MAP.get(code, ("Normal", "typical conditions"))
    data["condition_title"] = cond
    data["condition_desc"] = desc
    return data


def get_air_quality(latitude: float, longitude: float) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "us_aqi,pm2_5,pm10",
        "timezone": "auto"
    }
    resp = requests.get(AIR_QUALITY_API, params=params, timeout=5)
    resp.raise_for_status()
    return resp.json()


def get_climate_analytics(latitude: float, longitude: float) -> dict:
    today = datetime.now(timezone.utc).date()
    ref_date = today - timedelta(days=3652)
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": ref_date.isoformat(),
        "end_date": ref_date.isoformat(),
        "daily": "temperature_2m_mean",
        "timezone": "auto"
    }
    try:
        resp = requests.get(ARCHIVE_API, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        hist_temp = (daily.get("temperature_2m_mean") or [None])[0]
        return {
            "reference_date": ref_date.isoformat(),
            "historical_mean_temp_c": hist_temp,
            "years_ago": 10
        }
    except Exception as e:
        return {"historical_mean_temp_c": None, "error": str(e)}


CITY_ALIASES = {
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "bombay": "Mumbai",
    "calcutta": "Kolkata",
    "madras": "Chennai",
    "delhi": "New Delhi"
}

def search_locations(query_str: str) -> list:
    if not query_str or len(query_str.strip()) < 2:
        return []
    raw_key = query_str.strip().lower()
    search_term = CITY_ALIASES.get(raw_key, query_str.strip())
    cache_key = search_term.lower()

    if cache_key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[cache_key]

    params = {"name": search_term, "count": 6, "language": "en", "format": "json"}
    try:
        resp = requests.get(GEOCODE_API, params=params, timeout=4)
        resp.raise_for_status()
        results = resp.json().get("results", [])

        # Prioritize India results for Indian city queries
        def sort_priority(item):
            country = item.get("country", "").lower()
            name = item.get("name", "").lower()
            if country == "india":
                return 0
            return 1

        results = sorted(results, key=sort_priority)

        mapped = [
            {
                "name": item.get("name"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "country": item.get("country", ""),
                "admin1": item.get("admin1", ""),
                "display": f"{item.get('name')}, {item.get('admin1', '')} {item.get('country', '')}".strip()
            }
            for item in results
        ]
        _GEOCODE_CACHE[cache_key] = mapped
        return mapped
    except Exception:
        return []


def collect_weather_context(latitude: float, longitude: float) -> dict:
    cache_key = (round(latitude, 2), round(longitude, 2))
    now = time.time()
    if cache_key in _TELEMETRY_CACHE:
        cached_time, cached_data = _TELEMETRY_CACHE[cache_key]
        if now - cached_time < CACHE_TTL:
            return cached_data

    result = {"weather": {}, "air_quality": {}, "climate": {}, "errors": []}
    with ThreadPoolExecutor(max_workers=3) as executor:
        f_weather = executor.submit(get_live_weather, latitude, longitude)
        f_air = executor.submit(get_air_quality, latitude, longitude)
        f_climate = executor.submit(get_climate_analytics, latitude, longitude)

        try:
            result["weather"] = f_weather.result(timeout=6)
        except Exception as e:
            result["errors"].append(str(e))
        try:
            result["air_quality"] = f_air.result(timeout=6)
        except Exception as e:
            result["errors"].append(str(e))
        try:
            result["climate"] = f_climate.result(timeout=6)
        except Exception as e:
            result["errors"].append(str(e))

    if not result["errors"] and result["weather"]:
        _TELEMETRY_CACHE[cache_key] = (now, result)

    return result


# ============================================================
# DETERMINISTIC HAZARD & SEVERITY ENGINE (IMD Aligned)
# ============================================================

def analyze_weather_hazards(context: dict) -> list:
    alerts = []
    weather = context.get("weather", {})
    curr = weather.get("current", {})
    air_curr = context.get("air_quality", {}).get("current", {})

    temp = curr.get("temperature_2m")
    precip = curr.get("precipitation", 0)
    wind = curr.get("wind_speed_10m", 0)
    w_code = curr.get("weather_code", 0)
    aqi = air_curr.get("us_aqi")

    if isinstance(aqi, (int, float)):
        if aqi > 300:
            alerts.append({
                "event": "severe_smog",
                "severity": "CRITICAL",
                "imd_code": "RED",
                "message": "Hazardous smog alert. The air is dangerous to breathe.",
                "recommendation": "Stay strictly indoors with windows closed. Wear an N95 mask if going outside."
            })
        elif aqi > 150:
            alerts.append({
                "event": "poor_air_quality",
                "severity": "HIGH",
                "imd_code": "ORANGE",
                "message": "Unhealthy air quality advisory.",
                "recommendation": "Avoid outdoor workouts or jogging. Keep sensitive groups indoors."
            })

    if isinstance(temp, (int, float)):
        if temp >= 44.0:
            alerts.append({
                "event": "extreme_heatwave",
                "severity": "CRITICAL",
                "imd_code": "RED",
                "message": f"Severe heatwave warning ({temp}°C).",
                "recommendation": "High risk of sunstroke. Avoid direct sun between 11 AM - 4 PM and drink electrolytes."
            })
        elif temp >= 40.0:
            alerts.append({
                "event": "heatwave",
                "severity": "HIGH",
                "imd_code": "ORANGE",
                "message": f"Heatwave advisory ({temp}°C).",
                "recommendation": "Drink plenty of water and wear light cotton clothes. Avoid leaving kids in parked cars."
            })

    if isinstance(precip, (int, float)):
        if precip >= 25.0 or w_code in (82, 96, 99):
            alerts.append({
                "event": "cloudburst_flood",
                "severity": "CRITICAL",
                "imd_code": "RED",
                "message": f"Flash flood & cloudburst danger ({precip} mm/h rain).",
                "recommendation": "Move to higher ground immediately. Do NOT drive or walk through flooded waters."
            })
        elif precip >= 10.0:
            alerts.append({
                "event": "heavy_rain",
                "severity": "HIGH",
                "imd_code": "ORANGE",
                "message": "Heavy rain downpour warning.",
                "recommendation": "Expect road waterlogging and transit delays. Carry rain protection."
            })

    if isinstance(wind, (int, float)) and wind >= 65.0:
        alerts.append({
            "event": "cyclonic_winds",
            "severity": "CRITICAL",
            "imd_code": "RED",
            "message": f"Dangerous gale-force winds ({wind} km/h).",
            "recommendation": "Stay indoors away from glass windows and loose tin structures."
        })

    return alerts


def compute_aggregate_severity(alerts: list) -> Tuple[str, str]:
    rank_map = {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "LOW": 1, "NONE": 0}
    color_map = {"RED": 4, "ORANGE": 3, "YELLOW": 2, "GREEN": 1}

    max_rank = 0
    max_sev = "NONE"
    max_color = "GREEN"

    for a in alerts:
        sev = a.get("severity", "NONE")
        col = a.get("imd_code", "GREEN")
        r = rank_map.get(sev, 0)
        if r > max_rank:
            max_rank = r
            max_sev = sev
        if color_map.get(col, 1) > color_map.get(max_color, 1):
            max_color = col

    return max_sev, max_color


# ============================================================
# NATURAL LANGUAGE UNDERSTANDING & INTENT ROUTING
# ============================================================

def parse_user_input_and_context(
    query: str,
    session: ConversationSession,
    history: List[dict]
) -> Dict[str, Any]:
    """
    Understands:
    - Intent
    - Target location changes or references
    - Referenced date (today, tomorrow, weekend, etc.)
    - Referenced time (morning, afternoon, evening, night, specific hour)
    - Activity
    - Whether external weather data is required
    """
    q = query.lower().strip()

    # Strip trailing/leading punctuation for exact-match and prefix checks
    # e.g. "how are you?" -> "how are you",  "hello!" -> "hello"
    q_clean = re.sub(r"[?!.,;:\"\']+", "", q).strip()

    # 1. Check for location change patterns
    loc_match = re.search(
        r"(?:change|switch|set|move|update)\s+(?:the\s+)?(?:location|city)?\s*(?:to|in)\s+([a-zA-Z\s]+)",
        q
    )
    if not loc_match:
        loc_match = re.search(r"^(?:in|for|at)\s+([a-zA-Z\s]+)$", q)
    if not loc_match:
        loc_match = re.search(r"i(?:'m| am)\s+(?:in|at)\s+([a-zA-Z\s]+)", q)

    new_location_query = loc_match.group(1).strip() if loc_match else None

    # Check if query contains an explicit location mention via regex or SpaCy
    if not new_location_query:
        # e.g., "what's the weather in Bangalore tomorrow?"
        in_loc = re.search(r"(?:in|for|at|of)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)", q)
        if in_loc and in_loc.group(1).lower() not in ("the", "today", "tomorrow", "evening", "morning", "night", "my", "this", "our"):
            new_location_query = in_loc.group(1).strip()

    # 2. Extract referenced date
    referenced_date = session.referenced_date
    if any(w in q for w in ["tomorrow", "kal", "next day"]):
        referenced_date = "tomorrow"
    elif any(w in q for w in ["today", "aaj", "right now", "currently", "now"]):
        referenced_date = "today"
    elif any(w in q for w in ["weekend", "saturday", "sunday"]):
        referenced_date = "weekend"

    # 3. Extract referenced time
    referenced_time = session.referenced_time
    if any(w in q for w in ["morning", "am"]):
        referenced_time = "morning"
    elif any(w in q for w in ["afternoon", "noon", "midday"]):
        referenced_time = "afternoon"
    elif any(w in q for w in ["evening", "pm", "sundown", "sunset"]):
        referenced_time = "evening"
    elif any(w in q for w in ["night", "tonight", "late"]):
        referenced_time = "night"
    elif re.search(r"\b(?:at\s+)?([1-9]|1[0-2])\s*(?:o'clock|am|pm|\b)", q):
        m_hour = re.search(r"\b(?:at\s+)?([1-9]|1[0-2])\s*(?:o'clock|am|pm|\b)", q)
        if m_hour:
            referenced_time = m_hour.group(1)

    # 4. Intent Classification
    intent = "open_query"
    weather_needed = False

    # A. Casual / Social greetings & chit-chat — use q_clean so "hello!" / "hi?" match (WEATHER NOT NEEDED)
    if any(q_clean == w or q_clean.startswith(w + " ") for w in ["hi", "hello", "hey", "namaste", "good morning", "good afternoon", "good evening", "sup", "yo"]):
        intent = "greeting"
        weather_needed = False

    # Use q_clean so "how are you?" (q_clean="how are you") matches correctly
    elif any(q_clean == w or q_clean.startswith(w + " ") or q_clean.endswith(" " + w)
             for w in ["how are you", "how r u", "how are you doing",
                       "hows it going", "how are things", "how r you"]):
        intent = "how_are_you"
        weather_needed = False

    elif any(w in q for w in ["thanks", "thank you", "thx", "appreciate it"]):
        intent = "thanks"
        weather_needed = False

    elif any(w in q for w in ["bye", "goodbye", "see you", "good night", "cya"]):
        intent = "bye"
        weather_needed = False

    elif any(w in q for w in ["joke", "funny", "laugh", "tell me a joke"]):
        intent = "joke"
        weather_needed = False

    elif any(w in q for w in ["who are you", "what are you", "what can you do", "who created you"]):
        intent = "bot_identity"
        weather_needed = False

    elif any(w in q for w in ["that's crazy", "lol", "haha", "nice", "cool", "okay", "alright", "oh okay", "great"]):
        intent = "acknowledgement"
        weather_needed = False

    # B. Specific unrelated queries (WEATHER NOT NEEDED)
    elif any(w in q for w in ["shoe", "stepped on", "under my shoe", "gum"]):
        intent = "unrelated_shoe"
        weather_needed = False

    elif any(w in q for w in ["batman", "superman", "spider-man", "iron man", "who is", "capital of", "photosynthesis", "quantum"]):
        intent = "general_knowledge"
        weather_needed = False

    # C. Location Change
    elif any(q.startswith(p) for p in ["change location", "switch location", "set location", "switch to", "move to"]) and new_location_query:
        intent = "location_change"
        weather_needed = True

    # D. Weather Recommendations & Decision Support (WEATHER NEEDED)
    elif any(w in q for w in ["umbrella", "raincoat", "need an umbrella", "take an umbrella", "carry an umbrella", "should i take an umbrella"]):
        intent = "weather_recommendation"
        weather_needed = True

    elif any(w in q for w in ["run", "running", "jog", "jogging", "workout", "exercise", "walk", "marathon"]):
        intent = "outdoor_activity"
        session.last_activity = "running"
        weather_needed = True

    elif any(w in q for w in ["bike", "cycling", "motorcycle", "scooter", "drive", "driving", "commute", "road", "traffic"]):
        intent = "commuting"
        session.last_activity = "commuting"
        weather_needed = True

    elif any(w in q for w in ["wear", "jacket", "sweater", "clothes", "clothing", "dress"]):
        intent = "clothing_advice"
        weather_needed = True

    # Narrow: bare "dry" is too broad — only match explicit laundry phrases
    elif any(w in q for w in ["laundry", "drying clothes", "hang clothes", "dry my clothes"]):
        intent = "laundry"
        weather_needed = True

    # Narrow: bare "air" is too broad — require explicit air-quality terminology
    elif any(w in q for w in ["aqi", "air quality", "air pollution", "pollution", "smog", "mask", "asthma", "pm2", "pm10", "breathe"]):
        intent = "air_quality_query"
        weather_needed = True

    elif any(w in q for w in ["flood", "cyclone", "disaster", "danger", "safe", "evacuate", "emergency"]):
        intent = "disaster_query"
        weather_needed = True

    elif any(w in q for w in ["climate", "10 years", "history", "warming", "decade"]):
        intent = "climate_query"
        weather_needed = True

    elif any(w in q for w in ["tomorrow", "kal", "weekend", "evening", "tonight", "morning", "afternoon"]) \
            and any(w in q for w in ["rain", "will it", "weather", "what about", "how", "forecast", "storm", "sunny", "cloudy"]):
        intent = "forecast_query"
        weather_needed = True

    elif any(w in q for w in ["weather", "hot", "cold", "temp", "temperature", "rain", "humid", "wind", "breeze", "outside", "forecast"]):
        intent = "weather_query"
        weather_needed = True

    # Continuation context — follow-ups like "what about evening?", "will it rain?" after a weather exchange
    elif any(q_clean.startswith(w) or q_clean == w for w in ["what about", "how about", "and tomorrow", "will it", "is it", "what if"]):
        if session.last_intent in ("weather_query", "forecast_query", "weather_recommendation",
                                   "outdoor_activity", "commuting", "clothing_advice", "laundry"):
            intent = "forecast_query"
            weather_needed = True

    # Pure time/day reference follow-up: e.g. just "evening?" or "morning?" after forecast conversation
    elif any(w in q_clean for w in ["evening", "morning", "afternoon", "night", "tomorrow", "tonight"]):
        if session.last_intent in ("weather_query", "forecast_query", "weather_recommendation", "outdoor_activity"):
            intent = "forecast_query"
            weather_needed = True

    # Final safety net: if still open_query, check q_clean one more time for greetings missed by q
    if intent == "open_query":
        if any(q_clean == w or q_clean.startswith(w + " ")
               for w in ["hi", "hello", "hey", "namaste", "sup", "yo"]):
            intent = "greeting"
            weather_needed = False
        elif any(q_clean == w or q_clean.startswith(w + " ") or q_clean.endswith(" " + w)
                 for w in ["how are you", "how r u", "how are you doing", "hows it going", "how are things"]):
            intent = "how_are_you"
            weather_needed = False

    return {
        "intent": intent,
        "new_location_query": new_location_query,
        "referenced_date": referenced_date,
        "referenced_time": referenced_time,
        "weather_needed": weather_needed
    }


# ============================================================
# TIME-SPECIFIC FORECAST EXTRACTION
# ============================================================

def extract_specific_forecast(
    weather_data: dict,
    date_ref: str = "today",
    time_ref: Optional[str] = None
) -> dict:
    daily = weather_data.get("daily", {})
    hourly = weather_data.get("hourly", {})
    current = weather_data.get("current", {})

    day_idx = 1 if date_ref == "tomorrow" else (2 if date_ref == "weekend" else 0)

    # Daily basics
    t_max_list = daily.get("temperature_2m_max", [])
    t_min_list = daily.get("temperature_2m_min", [])
    rain_prob_list = daily.get("precipitation_probability_max", [])
    codes = daily.get("weather_code", [])

    day_max = round(t_max_list[day_idx]) if len(t_max_list) > day_idx and t_max_list[day_idx] is not None else round(current.get("temperature_2m", 25))
    day_min = round(t_min_list[day_idx]) if len(t_min_list) > day_idx and t_min_list[day_idx] is not None else round(day_max - 5)
    day_rain = rain_prob_list[day_idx] if len(rain_prob_list) > day_idx and rain_prob_list[day_idx] is not None else 20
    w_code = codes[day_idx] if len(codes) > day_idx else current.get("weather_code", 0)
    cond_desc = WMO_CODE_MAP.get(w_code, ("Normal", "typical conditions"))[1]

    # Specific hourly window if time_ref is set
    window_rain = day_rain
    window_temp = day_max

    if time_ref and hourly.get("time"):
        h_times = hourly.get("time", [])
        h_temps = hourly.get("temperature_2m", [])
        h_rains = hourly.get("precipitation_probability", [])

        # Filter to target day hours
        start_hour = 6
        end_hour = 11
        if time_ref == "morning":
            start_hour, end_hour = 6, 11
        elif time_ref == "afternoon":
            start_hour, end_hour = 12, 16
        elif time_ref in ("evening", "6"):
            start_hour, end_hour = 17, 21
        elif time_ref == "night":
            start_hour, end_hour = 21, 24

        day_offset = day_idx * 24
        window_indices = [day_offset + h for h in range(start_hour, min(end_hour + 1, 24)) if (day_offset + h) < len(h_times)]

        if window_indices:
            sub_temps = [h_temps[i] for i in window_indices if i < len(h_temps) and h_temps[i] is not None]
            sub_rains = [h_rains[i] for i in window_indices if i < len(h_rains) and h_rains[i] is not None]
            if sub_temps:
                window_temp = round(sum(sub_temps) / len(sub_temps))
            if sub_rains:
                window_rain = max(sub_rains)

    return {
        "day_max": day_max,
        "day_min": day_min,
        "rain_prob": window_rain,
        "temp": window_temp,
        "condition": cond_desc
    }


# ============================================================
# HIGH-QUALITY CONVERSATIONAL REASONING ENGINE
# ============================================================

def generate_conversational_response(
    query: str,
    session: ConversationSession,
    parsed: dict,
    weather_context: Optional[dict] = None,
    alerts: Optional[list] = None,
    api_key: Optional[str] = None
) -> str:
    """
    Generates direct, natural, human-like answers comparable to ChatGPT/Gemini.
    - No robotic templates.
    - Answers what the user asked.
    - Does not inject weather into unrelated chatter.
    """
    intent = parsed["intent"]
    city = session.city_name
    date_ref = session.referenced_date
    time_ref = session.referenced_time

    # 1. GREETING
    if intent == "greeting":
        return "Hey! What can I help you with?"

    # 2. HOW ARE YOU
    if intent == "how_are_you":
        return "I'm doing well. What's up?"

    # 3. ACKNOWLEDGEMENT / CASUAL
    if intent == "acknowledgement":
        return "Got it! Let me know if you need anything else."

    # 4. THANKS
    if intent == "thanks":
        return "You're welcome! Glad I could help."

    # 5. BYE
    if intent == "bye":
        return "Take care! Have a great one."

    # 6. JOKE
    if intent == "joke":
        return "Why did the cloud stay home from work? It was feeling a little *under the weather*! 😄"

    # 7. BOT IDENTITY
    if intent == "bot_identity":
        return "I'm WeatherGPT, a conversational assistant built to give you clear, everyday weather advice and disaster safety guidance without all the confusing raw charts."

    # 8. UNRELATED: SHOE
    if intent == "unrelated_shoe":
        return "Uh oh 😭 What did you step on?"

    # 9. GENERAL KNOWLEDGE / UNRELATED
    if intent == "general_knowledge":
        q_lower = query.lower()
        if "batman" in q_lower:
            return "Batman is a DC Comics superhero—the billionaire Bruce Wayne who protects Gotham City using intellect, martial arts, and high-tech gadgets."
        elif "superman" in q_lower:
            return "Superman is a DC Comics superhero from Krypton who lives as Clark Kent and protects Earth with superhuman abilities."
        elif "capital of" in q_lower:
            m = re.search(r"capital of\s+([a-zA-Z\s]+)", q_lower)
            country = m.group(1).strip() if m else "that country"
            return f"The capital of {country.title()} is a major administrative city. Let me know if you have any questions about the weather there!"
        return "That's outside my weather focus, but I'm happy to help if you have questions about your day, travel, or the forecast!"

    # 10. LOCATION CHANGE
    if intent == "location_change":
        return f"Got it — switching to {city}."

    # 11. OPEN / UNRECOGNIZED QUERY — respond conversationally without weather dump
    if intent == "open_query":
        return "I'm not quite sure what you meant — could you rephrase? I'm here to help with weather, forecasts, and outdoor planning!"

    # If we need weather data, ensure we have it
    if not weather_context or not weather_context.get("weather"):
        return f"I couldn't pull the latest weather for {city} right now. Please try again in a moment."

    weather = weather_context["weather"]
    current = weather.get("current", {})
    air = weather_context.get("air_quality", {}).get("current", {})
    aqi = round(air.get("us_aqi", 50))
    alerts_list = alerts or []

    # Check severe safety
    safety_warning = ""
    if alerts_list:
        top_alert = alerts_list[0]
        if top_alert.get("severity") in ("CRITICAL", "HIGH"):
            safety_warning = f"⚠️ **Safety Warning:** {top_alert['message']} {top_alert['recommendation']}\n\n"

    # Pull specific forecast for date/time window
    fc = extract_specific_forecast(weather, date_ref=date_ref, time_ref=time_ref)
    target_time_desc = f"{date_ref} {time_ref}" if time_ref else date_ref

    # 11. UMBRELLA RECOMMENDATION
    if intent == "weather_recommendation":
        if fc["rain_prob"] >= 40:
            if time_ref:
                return f"{safety_warning}Yeah, I'd take an umbrella. With showers likely in {city} around {target_time_desc} (about a {fc['rain_prob']}% chance), having one with you will keep you covered."
            else:
                return f"{safety_warning}Yeah, I'd carry an umbrella. There's a decent {fc['rain_prob']}% chance of rain in {city} {date_ref}."
        else:
            return f"{safety_warning}You won't need an umbrella {target_time_desc} in {city}. Rain chance is low at only {fc['rain_prob']}%."

    # 12. OUTDOOR ACTIVITY (Running / Jogging / Sports)
    if intent == "outdoor_activity":
        # Check running conditions
        issues = []
        if aqi > 140:
            issues.append(f"air quality is unhealthy (AQI {aqi})")
        if fc["rain_prob"] > 55:
            issues.append(f"showers are likely ({fc['rain_prob']}% rain chance)")
        if fc["temp"] >= 37:
            issues.append(f"it will be quite hot ({fc['temp']}°C)")

        if issues:
            return f"{safety_warning}I'd reconsider running {target_time_desc} in {city} because {', and '.join(issues)}. If you can, stick to an indoor treadmill or wait for a clearer window."
        else:
            return f"{safety_warning}{target_time_desc.capitalize()} looks good for a run in {city}! Temperatures should be around {fc['temp']}°C with clean air and minimal rain risk."

    # 13. COMMUTING / BIKING
    if intent == "commuting":
        if fc["rain_prob"] >= 45 or current.get("precipitation", 0) > 1:
            return f"{safety_warning}Rain could slow down your commute {target_time_desc} in {city}. With a {fc['rain_prob']}% chance of showers, roads will be slick—so leave a few minutes early and watch your braking distance if you're on a two-wheeler."
        else:
            return f"{safety_warning}Commuting looks clear {target_time_desc} in {city}. Roads should be dry with calm travel conditions."

    # 14. FORECAST QUERY (e.g., "will it rain tomorrow?", "what about evening?")
    if intent == "forecast_query":
        rain_text = f"a {fc['rain_prob']}% chance of rain" if fc["rain_prob"] >= 30 else "little to no rain expected"
        if time_ref:
            return f"{safety_warning}For {city} {target_time_desc}, expect {fc['condition']} around {fc['temp']}°C with {rain_text}."
        elif date_ref == "tomorrow":
            rain_adv = "Keep an umbrella handy just in case." if fc["rain_prob"] >= 40 else "It should stay mostly dry."
            return f"{safety_warning}Tomorrow in {city}, expect highs around {fc['day_max']}°C with {fc['condition']} and {rain_text}. {rain_adv}"
        elif date_ref == "weekend":
            return f"{safety_warning}This weekend in {city}, expect temperatures around {fc['day_max']}°C with {fc['condition']}."
        else:
            return f"{safety_warning}For {city} {target_time_desc}, conditions look like {fc['condition']} around {fc['temp']}°C."

    # 15. WEATHER QUERY (e.g., "what's the weather?")
    if intent == "weather_query":
        curr_temp = round(current.get("temperature_2m", fc["temp"]))
        feels = round(current.get("apparent_temperature", curr_temp))
        cond = weather.get("condition_desc", "fair conditions")
        rain_prob = fc["rain_prob"]

        if "humid" in query.lower():
            humidity = round(current.get("relative_humidity_2m", 60))
            return f"{safety_warning}Humidity in {city} is currently {humidity}%, which is why it feels warm and sticky ({feels}°C) even though the actual temperature is {curr_temp}°C."
        elif "hot" in query.lower() or "temperature" in query.lower():
            return f"{safety_warning}It's currently {curr_temp}°C in {city}, feeling like {feels}°C."
        else:
            return f"{safety_warning}In {city} right now, it's {cond} around {curr_temp}°C (feels like {feels}°C) with a {rain_prob}% chance of rain."

    # 16. CLOTHING ADVICE
    if intent == "clothing_advice":
        temp_val = fc["temp"]
        if temp_val >= 30:
            return f"{safety_warning}Light, breathable cotton clothes are your best bet in {city} ({temp_val}°C). Keep sunglasses with you."
        elif temp_val <= 16:
            return f"{safety_warning}It's on the cooler side in {city} ({temp_val}°C). A light jacket, hoodie, or sweater will keep you comfortable."
        else:
            return f"{safety_warning}Casual everyday clothes like a t-shirt and jeans will be totally fine ({temp_val}°C)."

    # 17. AIR QUALITY QUERY
    if intent == "air_quality_query":
        if aqi > 150:
            return f"{safety_warning}The air in {city} is quite poor today (AQI {aqi}). If you're sensitive to dust or have asthma, wear an N95 mask outside."
        else:
            return f"{safety_warning}The air quality in {city} is good today (AQI {aqi}), so you can breathe easily outside."

    # 18. DISASTER QUERY
    if intent == "disaster_query":
        if alerts_list:
            top_a = alerts_list[0]
            return f"⚠️ **Alert for {city}:** {top_a['message']} {top_a['recommendation']} For emergency help, dial **112** or **1078**."
        else:
            return f"Everything is calm in {city} right now with no active flood or severe storm warnings."

    # 19. CLIMATE QUERY
    if intent == "climate_query":
        climate = weather_context.get("climate", {})
        hist = climate.get("historical_mean_temp_c")
        if hist is not None:
            curr_temp = round(current.get("temperature_2m", 25))
            diff = round(curr_temp - hist, 1)
            diff_str = f"{abs(diff)}°C warmer" if diff > 0 else f"{abs(diff)}°C cooler"
            return f"Compared to 10 years ago today, {city} is about {diff_str}. That reflects the gradual seasonal warming we've observed over the past decade."
        return f"Historical records show {city} experiencing typical seasonal temperatures for this time of year."

    # 20. LAUNDRY
    if intent == "laundry":
        if fc["rain_prob"] >= 40:
            return f"{safety_warning}Not a good time to hang laundry outside in {city}—there's a {fc['rain_prob']}% chance of rain, so clothes could get soaked."
        else:
            return f"{safety_warning}Yes, it's a good day for outdoor laundry in {city}. Weather should stay dry enough for clothes to dry."

    # Fallback
    curr_temp = round(current.get("temperature_2m", 25))
    cond = weather.get("condition_desc", "fair conditions")
    return f"{safety_warning}In {city}, it's currently {cond} around {curr_temp}°C."


# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "WeatherGPT Intelligence Platform",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "local_nlp_ready": nlp is not None,
        "openai_configured": bool(OPENAI_API_KEY)
    }


@app.get("/api/geocode")
def geocode_city(q: str = Query(..., min_length=2)):
    results = search_locations(q)
    return {"query": q, "results": results}


@app.get("/api/dashboard")
def dashboard_endpoint(
    latitude: float = Query(28.6139, ge=-90, le=90),
    longitude: float = Query(77.2090, ge=-180, le=180),
    city: str = Query("Current Location"),
    db: Session = Depends(get_db)
):
    return get_comprehensive_weather(lat=latitude, lon=longitude, city=city, db=db)


@app.get("/api/weather")
def get_comprehensive_weather(
    lat: float = Query(28.6139, ge=-90, le=90),
    lon: float = Query(77.2090, ge=-180, le=180),
    city: str = Query("New Delhi"),
    db: Session = Depends(get_db)
):
    context = collect_weather_context(lat, lon)
    alerts = analyze_weather_hazards(context)
    severity, imd_color = compute_aggregate_severity(alerts)

    if severity in ("HIGH", "CRITICAL") and alerts:
        for a in alerts:
            history_rec = AlertHistory(
                location_name=city,
                event=a.get("event", "weather_hazard"),
                severity=a.get("severity", "HIGH"),
                imd_color=a.get("imd_code", "ORANGE"),
                description=a.get("message", ""),
                delivered=True
            )
            db.add(history_rec)
        db.commit()

    disaster_guide = None
    if alerts:
        disaster_guide = get_protocol_for_hazard(alerts[0]["event"])

    return {
        "location": {
            "city": city,
            "latitude": lat,
            "longitude": lon
        },
        "severity": severity,
        "imd_color": imd_color,
        "alerts": alerts,
        "telemetry": context,
        "disaster_guide": disaster_guide,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post("/api/chat")
def chat_endpoint(request: QueryRequest, db: Session = Depends(get_db)):
    """
    Main Conversational AI Endpoint.
    Executes Intent Understanding -> Context Resolution -> Decides on Weather -> Answers Directly.
    """
    session = get_or_create_session(
        request.session_id or "default",
        request.city_name or "New Delhi",
        request.latitude,
        request.longitude
    )

    history_dicts = [m.model_dump() for m in request.history]

    # STEP 1: Understand Intent & Context
    parsed = parse_user_input_and_context(request.message, session, history_dicts)

    # STEP 2: Handle Location Change or Location Mentions
    if parsed["new_location_query"]:
        geo_hits = search_locations(parsed["new_location_query"])
        if geo_hits:
            hit = geo_hits[0]
            session.update_location(hit["name"], hit["latitude"], hit["longitude"])

    # Update session temporal tracking
    session.referenced_date = parsed["referenced_date"]
    if parsed["referenced_time"]:
        session.referenced_time = parsed["referenced_time"]
    session.last_intent = parsed["intent"]

    # STEP 3: Decide Whether Weather Data is Needed
    weather_context = None
    alerts = []
    severity = "NONE"
    imd_color = "GREEN"

    if parsed["weather_needed"]:
        weather_context = collect_weather_context(session.latitude, session.longitude)
        alerts = analyze_weather_hazards(weather_context)
        severity, imd_color = compute_aggregate_severity(alerts)
        session.last_weather = weather_context

    # STEP 4: Generate Response (OpenAI LLM if API key provided, or Conversational Engine)
    client = get_openai_client(request.api_key)

    if client:
        # Prompt grounded LLM
        weather_snippet = ""
        if weather_context and parsed["weather_needed"]:
            # Extract only what the LLM actually needs instead of the raw full JSON dump
            w = weather_context.get("weather", {})
            curr = w.get("current", {})
            daily = w.get("daily", {})
            air_curr = weather_context.get("air_quality", {}).get("current", {})
            weather_snippet = (
                f"\nVERIFIED WEATHER DATA FOR {session.city_name}:\n"
                f"  Current temp: {curr.get('temperature_2m', 'N/A')}°C, "
                f"feels like {curr.get('apparent_temperature', 'N/A')}°C\n"
                f"  Humidity: {curr.get('relative_humidity_2m', 'N/A')}%\n"
                f"  Wind: {curr.get('wind_speed_10m', 'N/A')} km/h\n"
                f"  Precipitation now: {curr.get('precipitation', 0)} mm/h\n"
                f"  Today max/min: {daily.get('temperature_2m_max', ['N/A'])[0]}°C / {daily.get('temperature_2m_min', ['N/A'])[0]}°C\n"
                f"  Tomorrow max/min: {daily.get('temperature_2m_max', ['N/A', 'N/A'])[1] if len(daily.get('temperature_2m_max', [])) > 1 else 'N/A'}°C / "
                f"{daily.get('temperature_2m_min', ['N/A', 'N/A'])[1] if len(daily.get('temperature_2m_min', [])) > 1 else 'N/A'}°C\n"
                f"  Today rain prob: {daily.get('precipitation_probability_max', ['N/A'])[0]}%\n"
                f"  Tomorrow rain prob: {daily.get('precipitation_probability_max', ['N/A', 'N/A'])[1] if len(daily.get('precipitation_probability_max', [])) > 1 else 'N/A'}%\n"
                f"  AQI (US): {air_curr.get('us_aqi', 'N/A')}\n"
                f"ACTIVE ALERTS: {json.dumps(alerts) if alerts else 'None'}"
            )

        intent_hint = parsed["intent"]
        date_hint = session.referenced_date or "today"
        time_hint = session.referenced_time or "any time"

        system_prompt = f"""You are WeatherGPT — a friendly, conversational weather assistant. Respond like a smart friend, not a weather app.

CONVERSATION CONTEXT:
- Active location: {session.city_name}
- Detected user intent: {intent_hint}
- Referenced date in conversation: {date_hint}
- Referenced time in conversation: {time_hint}

STRICT RULES:
1. Answer what the user ACTUALLY asked. Do NOT redirect casual messages to weather.
2. Casual messages ("hello", "how are you?", "thanks", "lol", "something under my shoe") → respond naturally with NO weather info.
3. When answering weather questions: use the VERIFIED DATA below. Never invent temperatures, rain %, AQI, or locations.
4. Keep answers concise — 1-3 sentences for simple questions; 2-5 for decision support.
5. Never use raw numbered lists or bullet sensor dumps. Speak in natural sentences.
6. Do NOT start every weather answer with "In [city], it's currently...". Vary your phrasing.
7. For activity/umbrella/outdoor questions: give a direct recommendation first, then the supporting reason.
8. If severe weather alerts exist, mention safety FIRST.
9. The user does not need to repeat location/time — use the conversation context above.
{weather_snippet}
"""
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history_dicts[-8:]:
            if msg.get("role") in ("user", "assistant"):
                messages.append(msg)
        messages.append({"role": "user", "content": request.message})

        try:
            completion = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=300
            )
            reply = completion.choices[0].message.content or "I'm here to help!"
        except Exception:
            reply = generate_conversational_response(
                request.message, session, parsed, weather_context, alerts, request.api_key
            )
    else:
        reply = generate_conversational_response(
            request.message, session, parsed, weather_context, alerts, request.api_key
        )

    return {
        "response": reply,
        "severity": severity,
        "imd_color": imd_color,
        "alerts": alerts,
        "location": {
            "city": session.city_name,
            "latitude": session.latitude,
            "longitude": session.longitude
        }
    }


@app.get("/api/alerts")
def get_recent_alerts(db: Session = Depends(get_db)):
    records = db.query(AlertHistory).order_by(AlertHistory.timestamp.desc()).limit(25).all()
    return [
        {
            "id": r.id,
            "location": r.location_name,
            "event": r.event,
            "severity": r.severity,
            "imd_color": r.imd_color,
            "description": r.description,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "delivered": r.delivered
        }
        for r in records
    ]


@app.post("/api/alerts/simulate")
def simulate_disaster_scenario(req: SimulateAlertRequest, db: Session = Depends(get_db)):
    guide = get_protocol_for_hazard(req.scenario)
    alert_entry = AlertHistory(
        location_name=req.city_name,
        event=f"simulated_{req.scenario}",
        severity="CRITICAL" if guide["imd_code"] == "RED" else "HIGH",
        imd_color=guide["imd_code"],
        description=f"[SIMULATION DRILL] {guide['title']}: Immediate life safety directives activated.",
        delivered=True
    )
    db.add(alert_entry)
    db.commit()

    return {
        "status": "simulation_triggered",
        "scenario": req.scenario,
        "imd_color": guide["imd_code"],
        "guide": guide
    }


@app.get("/api/emergency-guide")
def get_emergency_knowledge_base():
    return DISASTER_PROTOCOLS


@app.post("/api/sms-fallback")
async def sms_emergency_handler(
    request: Request,
    From: Optional[str] = Form(None),
    Body: Optional[str] = Form(None)
):
    query_body = ""
    if Body:
        query_body = Body.strip()
    else:
        try:
            json_data = await request.json()
            query_body = json_data.get("message") or json_data.get("Body", "")
        except Exception:
            pass

    lat, lon = 28.6139, 77.2090
    city_name = "Target Zone"

    parts = query_body.strip().split()
    for part in parts:
        if "," in part:
            try:
                p_lat, p_lon = map(float, part.split(","))
                lat, lon = p_lat, p_lon
            except Exception:
                pass
        else:
            hits = search_locations(part)
            if hits:
                lat = hits[0]["latitude"]
                lon = hits[0]["longitude"]
                city_name = hits[0]["name"]
                break

    context = collect_weather_context(lat, lon)
    alerts = analyze_weather_hazards(context)
    curr = context.get("weather", {}).get("current", {})
    temp = curr.get("temperature_2m", "N/A")
    rain = curr.get("precipitation", 0)

    if alerts:
        top_alert = alerts[0]
        sms_text = f"[WeatherGPT {top_alert['imd_code']}] {city_name}: {top_alert['message'][:80]} Adv: {top_alert['recommendation'][:60]}. Dial 112."
    else:
        sms_text = f"[WeatherGPT OK] {city_name}: {temp}C, Rain {rain}mm. Conditions normal. Dial 112 if emergency."

    sms_text = sms_text[:160]

    twiml_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{sms_text}</Message>
</Response>"""

    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header or request.headers.get("content-type") == "application/json":
        return {
            "sms_text": sms_text,
            "char_count": len(sms_text),
            "location": city_name,
            "alerts": alerts
        }

    return Response(content=twiml_xml, media_type="application/xml")


# ============================================================
# STATIC FILES SERVING
# ============================================================

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    def serve_frontend():
        index_file = os.path.join(static_dir, "index.html")
        if os.path.exists(index_file):
            with open(index_file, "r", encoding="utf-8") as f:
                return f.read()
        return "<h1>WeatherGPT UI is loading...</h1>"
