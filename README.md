# WeatherGPT
This is the first project of Team Cryptic for SIH 2026
PSID- SIH26068

# WeatherGPT: AI Weather & Disaster Intelligence Command Center
**Smart India Hackathon 2026** — Problem Statement ID: **SIH26068**  
**Theme:** Disaster Management | **Category:** Software | **Team:** Cryptic (Team ID: 102)
---
## 🌟 Executive Summary
**WeatherGPT** is a next-generation conversational weather forecasting, proactive alert, climate intelligence, and disaster management command platform. Unlike generic text-based chatbots (such as standard ChatGPT or Gemini clones) that passively wait for questions and lack deterministic hazard grounding, WeatherGPT is purpose-built as an **authoritative disaster intelligence console**:
1. **Deterministic Hazard Severity Engine**: Evaluates live meteorological conditions against **IMD (India Meteorological Department)** alert color codes (`GREEN`, `YELLOW`, `ORANGE`, `RED`), guaranteeing zero hallucination during life-safety crises.
2. **Proactive Alert Broadcast**: Automatically broadcasts hazard warnings (flash floods, cyclones, severe heatwaves, toxic AQI smog, cloudbursts) before the user even enters a prompt.
3. **10-Year Climate Anomaly Tracking**: Queries high-resolution atmospheric reanalysis archive (Open-Meteo Archive) to compute long-term temperature anomalies and micro-climate shifts compared to 10 years ago today.
4. **Hybrid AI & Local NLP**: Functions 100% locally out-of-the-box using SpaCy (`en_core_web_sm`) and meteorological expert heuristics with zero API costs, and seamlessly upgrades to OpenAI GPT-4o with tool-calling whenever an API key is supplied.
5. **Emergency Low-Bandwidth SMS Fallback**: A Twilio-compatible webhook and simulated feature-phone console that condenses critical forecast and evacuation advice into 160 characters for citizens caught in data network blackouts.
6. **Voice & Multimodal Briefing**: Supports Web Speech API for voice queries and audio speech synthesis for auditory hazard alerts.
---
## 🏗️ Architecture & Technology Stack
```mermaid
graph TD
    User([Citizen / Emergency Manager]) <--> UI[WeatherGPT Command Center UI]
    User -- SMS SOS --> SMSWebhook[Twilio / SMS Fallback Webhook]
    subgraph Frontend [Modern Single-Page Application]
        UI --> HeroCard[Real-Time Conditions Hero]
        UI --> Gauges[US AQI, UV Index & Climate Delta Gauges]
        UI --> TrendChart[24h Temperature & Rain Probability Chart]
        UI --> GISMap[Leaflet GIS Hazard Radar]
        UI --> Preparedness[NDMA Evacuation Go-Bag Checklist]
        UI --> ChatPanel[Conversational Co-Pilot with Audio Voice]
    end
    subgraph Backend [FastAPI Server on :8000]
        Endpoints["REST Endpoints (/api/weather, /api/chat, /api/alerts, /api/geocode, /api/sms-fallback)"]
        
        subgraph Engine [Hybrid Intelligence & Severity Engine]
            SpacyNLP["Local SpaCy NLP & Intent Parser"]
            DeterministicRules["Deterministic Hazard Engine (IMD Aligned)"]
            OpenAIEngine["OpenAI GPT-4o Reasoning (Optional / BYOK)"]
        end
        subgraph Connectors [Multi-Source Data Connectors]
            OMForecast["Open-Meteo Live Forecast API"]
            OMAirQuality["Open-Meteo Air Quality API (AQI, PM2.5, PM10)"]
            OMArchive["Open-Meteo Climate Archive API (10Y Baseline)"]
            OMGeocode["Open-Meteo Geocoding API (Global Cities)"]
        end
        subgraph Storage [SQLite Database]
            DB[(weathergpt.db)]
