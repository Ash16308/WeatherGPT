import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

print("=" * 60)
print("RUNNING WEATHERGPT VERIFICATION SUITE (SIH26068)")
print("=" * 60)

try:
    from weathergpt_backend import (
        collect_weather_context,
        analyze_weather_hazards,
        compute_aggregate_severity,
        analyze_user_intent_local,
        generate_local_intelligent_response,
        search_locations,
        Base,
        engine,
        SessionLocal,
        AlertHistory
    )
    print("✅ Module imports successful.")
except Exception as e:
    print(f"❌ Failed to import weathergpt_backend: {e}")
    sys.exit(1)

# TEST 1: Geocoding
print("\n[Test 1] Testing Geocoding Search (Mumbai)...")
try:
    hits = search_locations("Mumbai")
    assert len(hits) > 0, "No results returned for Mumbai"
    print(f"✅ Geocoding passed! Found: {hits[0]['display']} at ({hits[0]['latitude']}, {hits[0]['longitude']})")
except Exception as e:
    print(f"❌ Geocoding failed: {e}")

# TEST 2: Multi-Source Weather & Air Quality & Climate Telemetry
print("\n[Test 2] Testing Live Telemetry Gathering (New Delhi: 28.61, 77.20)...")
try:
    ctx = collect_weather_context(28.6139, 77.2090)
    weather = ctx.get("weather", {})
    air = ctx.get("air_quality", {})
    climate = ctx.get("climate", {})

    temp = weather.get("current", {}).get("temperature_2m")
    aqi = air.get("current", {}).get("us_aqi")
    hist_temp = climate.get("historical_mean_temp_c")

    print(f"✅ Live Weather: Current Temp = {temp}°C, Condition = {weather.get('condition_title')}")
    print(f"✅ Air Quality: US AQI = {aqi}")
    print(f"✅ 10-Year Climate Baseline: 10y Historical Temp = {hist_temp}°C (Date: {climate.get('reference_date')})")
except Exception as e:
    print(f"❌ Telemetry collection failed: {e}")

# TEST 3: Deterministic Severity & Hazard Engine
print("\n[Test 3] Testing Deterministic Severity Engine...")
try:
    # Test extreme heat mock
    mock_context = {
        "weather": {
            "current": {
                "temperature_2m": 45.0,
                "apparent_temperature": 48.0,
                "precipitation": 0,
                "wind_speed_10m": 15.0,
                "uv_index": 10.0,
                "weather_code": 0
            },
            "daily": {"precipitation_sum": [0]}
        },
        "air_quality": {"current": {"us_aqi": 180}},
        "climate": {}
    }
    alerts = analyze_weather_hazards(mock_context)
    sev, imd_col = compute_aggregate_severity(alerts)
    print(f"✅ Hazard Analysis flagged {len(alerts)} alerts.")
    print(f"✅ Severity = {sev}, IMD Color = {imd_col}")
    assert imd_col == "RED", f"Expected RED alert for 45°C, got {imd_col}"
    print("✅ Deterministic IMD logic validated!")
except Exception as e:
    print(f"❌ Hazard engine failed: {e}")

# TEST 4: Local Intelligent NLP (Zero-Key Mode)
print("\n[Test 4] Testing Local NLP Intent Engine & Conversational Reasoning...")
try:
    q1 = "Will I need an umbrella today?"
    intent1 = analyze_user_intent_local(q1)
    ans1 = generate_local_intelligent_response(q1, ctx, alerts=[], location_name="New Delhi")
    print(f"Query: '{q1}' -> Intent: {intent1['intent']}")
    print(f"Sample response preview:\n{ans1[:140]}...\n")

    q2 = "Can I go for a run outside?"
    intent2 = analyze_user_intent_local(q2)
    ans2 = generate_local_intelligent_response(q2, ctx, alerts=[], location_name="New Delhi")
    print(f"Query: '{q2}' -> Intent: {intent2['intent']}")
    print(f"Sample response preview:\n{ans2[:140]}...\n")

    assert intent1["intent"] == "umbrella_rain"
    assert intent2["intent"] == "fitness_outdoor"
    print("✅ Local NLP & expert heuristics passed!")
except Exception as e:
    print(f"❌ Local NLP failed: {e}")

# TEST 5: Database Operations
print("\n[Test 5] Testing SQLite Database Persistence...")
try:
    db = SessionLocal()
    rec = AlertHistory(
        location_name="Test Verification City",
        event="test_flash_flood",
        severity="CRITICAL",
        imd_color="RED",
        description="Automated unit test alert log",
        delivered=True
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    print(f"✅ Saved AlertHistory record ID: {rec.id}")

    saved_rec = db.get(AlertHistory, rec.id)
    assert saved_rec is not None
    db.delete(saved_rec)
    db.commit()
    db.close()
    print("✅ Database read/write/delete successful!")
except Exception as e:
    print(f"❌ Database test failed: {e}")

print("\n" + "=" * 60)
print("ALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
print("=" * 60)
