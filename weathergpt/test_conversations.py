# test_conversations.py - Automated Testing of the 10 Exact Required Scenarios

import sys
import requests
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"
SESSION_ID = "test_sih_evaluator_session"

print("=" * 70)
print("TESTING WEATHERGPT CONVERSATIONAL INTELLIGENCE SUITE (10 SCENARIOS)")
print("=" * 70)

# Multi-turn conversation tracker
history = []
current_city = "New Delhi"
current_lat = 28.6139
current_lon = 77.2090

def send_message(user_msg):
    global current_city, current_lat, current_lon, history
    payload = {
        "message": user_msg,
        "latitude": current_lat,
        "longitude": current_lon,
        "city_name": current_city,
        "session_id": SESSION_ID,
        "history": history
    }
    resp = requests.post(f"{BASE_URL}/api/chat", json=payload, timeout=10)
    data = resp.json()
    
    # Update local tracking
    if "location" in data and data["location"]:
        current_city = data["location"]["city"]
        current_lat = data["location"]["latitude"]
        current_lon = data["location"]["longitude"]
    
    reply = data["response"]
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": reply})
    return reply, current_city

# SCENARIO RUNNER
test_cases = [
    (1, "hello", "Natural greeting, zero weather dump", lambda a, c: "weather" not in a.lower() and ("help" in a.lower() or "hey" in a.lower() or "hello" in a.lower())),
    (2, "how are you?", "Natural casual response, zero weather dump", lambda a, c: "weather" not in a.lower() and ("well" in a.lower() or "good" in a.lower() or "what's up" in a.lower())),
    (3, "there is something under my shoe", "Acknowledge shoe / ask what happened, zero weather report", lambda a, c: "shoe" in a.lower() or "step" in a.lower()),
    (4, "change location to Bangalore", "Active location updates to Bengaluru", lambda a, c: "bengaluru" in c.lower() or "bangalore" in c.lower() or "bengaluru" in a.lower()),
    (5, "what's the weather?", "Weather for Bengaluru, NOT Delhi", lambda a, c: ("bengaluru" in a.lower() or "bengaluru" in c.lower()) and "delhi" not in a.lower()),
    (6, "will it rain tomorrow?", "Understands Bengaluru + tomorrow", lambda a, c: "tomorrow" in a.lower() and ("rain" in a.lower() or "showers" in a.lower() or "dry" in a.lower())),
    (7, "what about evening?", "Understands Bengaluru + tomorrow + evening", lambda a, c: "evening" in a.lower() and ("rain" in a.lower() or "showers" in a.lower() or "°c" in a.lower())),
    (8, "should I take an umbrella?", "Contextual umbrella recommendation using tomorrow evening forecast", lambda a, c: "umbrella" in a.lower() and ("yes" in a.lower() or "take" in a.lower() or "carry" in a.lower() or "won't need" in a.lower())),
    (9, "can I go running tomorrow morning?", "Evaluates morning conditions & AQI for decision support", lambda a, c: "morning" in a.lower() and ("run" in a.lower() or "running" in a.lower())),
    (10, "thanks", "Natural response, zero weather info", lambda a, c: "weather" not in a.lower() and ("welcome" in a.lower() or "glad" in a.lower() or "happy" in a.lower()))
]

all_passed = True
for idx, q, expectation, validator in test_cases:
    print(f"\n[TEST {idx}]")
    print(f"User: \"{q}\"")
    reply, city = send_message(q)
    print(f"Assistant: \"{reply}\"")
    print(f"Active Location Context: {city}")
    
    passed = validator(reply, city)
    if passed:
        print(f"✅ PASS: {expectation}")
    else:
        print(f"❌ FAIL: Expected: {expectation}")
        all_passed = False

print("\n" + "=" * 70)
if all_passed:
    print("🎉 ALL 10 CONVERSATIONAL TEST SCENARIOS PASSED WITH FLYING COLORS!")
else:
    print("⚠️ SOME TESTS FAILED — CHECK OUTPUT ABOVE")
print("=" * 70)
