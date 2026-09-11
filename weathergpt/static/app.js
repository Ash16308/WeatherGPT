// app.js - WeatherGPT Conversational Weather & Disaster AI

const state = {
  lat: 28.6139,
  lon: 77.2090,
  city: "New Delhi",
  telemetry: null,
  chatHistory: [],
  hourlyChart: null,
  leafletMap: null,
  mapMarker: null,
  hazardCircle: null,
  isRecording: false,
  speechSynthActive: false,
  autoSpeak: localStorage.getItem("weathergpt_auto_speak") === "true",
  apiKey: localStorage.getItem("weathergpt_openai_key") || "",
  disasterProtocols: null,
  activeSection: "section-chat",
  sessionId: "sess_" + Math.random().toString(36).substring(2, 9)
};

const CODE_ICONS = {
  0: "sun", 1: "sun", 2: "cloud-sun", 3: "cloud", 45: "cloud-fog",
  51: "cloud-drizzle", 61: "cloud-rain", 63: "cloud-rain", 65: "cloud-rain",
  71: "cloud-snow", 80: "cloud-rain", 95: "cloud-lightning"
};

document.addEventListener("DOMContentLoaded", async () => {
  lucide.createIcons();

  initNavigation();
  initSettings();
  initEventHandlers();
  initSpeechRecognition();
  await loadEmergencyGuides();
  await refreshTelemetry(state.lat, state.lon, state.city);
});

// ============================================================
// NAVIGATION & VIEW SWITCHER
// ============================================================
function initNavigation() {
  document.querySelectorAll(".nav-section-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const targetSec = btn.getAttribute("data-section");
      switchSection(targetSec);
    });
  });

  document.querySelectorAll(".btn-back-to-chat").forEach(b => {
    b.addEventListener("click", () => {
      switchSection("section-chat");
      document.getElementById("chatInput").focus();
    });
  });

  const sidebar = document.getElementById("appSidebar");
  const btnToggle = document.getElementById("btnToggleSidebar");
  const btnClose = document.getElementById("btnCloseSidebarMobile");

  if (btnToggle) {
    btnToggle.addEventListener("click", () => sidebar.classList.remove("-translate-x-full"));
  }
  if (btnClose) {
    btnClose.addEventListener("click", () => sidebar.classList.add("-translate-x-full"));
  }

  // New Chat Button
  document.getElementById("btnNewChat").addEventListener("click", () => {
    state.chatHistory = [];
    state.sessionId = "sess_" + Math.random().toString(36).substring(2, 9);
    document.getElementById("chatStream").innerHTML = `
      <div class="text-left text-sm text-slate-300 leading-relaxed py-2">
        <p class="font-medium text-white mb-1">New conversation started.</p>
        <p class="text-slate-400">Ask me anything about today's weather, commuting, outdoor plans, or safety.</p>
      </div>
    `;
    switchSection("section-chat");
    lucide.createIcons();
  });
}

function switchSection(sectionId) {
  state.activeSection = sectionId;

  document.querySelectorAll(".app-section").forEach(sec => sec.classList.add("hidden"));
  const target = document.getElementById(sectionId);
  if (target) target.classList.remove("hidden");

  document.querySelectorAll(".nav-section-btn").forEach(btn => {
    if (btn.getAttribute("data-section") === sectionId) {
      btn.className = "nav-section-btn active w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium bg-[#222738] text-white";
    } else {
      btn.className = "nav-section-btn w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-slate-400 hover:bg-[#1a1e2b] hover:text-slate-200 transition-colors";
    }
  });

  const sidebar = document.getElementById("appSidebar");
  if (window.innerWidth < 768) {
    sidebar.classList.add("-translate-x-full");
  }

  if (sectionId === "section-map") {
    if (!state.leafletMap) initMap();
    else setTimeout(() => state.leafletMap.invalidateSize(), 150);
  } else if (sectionId === "section-forecast" && state.hourlyChart) {
    setTimeout(() => state.hourlyChart.resize(), 150);
  }

  lucide.createIcons();
}

// ============================================================
// MAP INITIALIZATION
// ============================================================
function initMap() {
  const mapContainer = document.getElementById("weatherMap");
  if (!mapContainer || state.leafletMap) return;

  state.leafletMap = L.map("weatherMap", { zoomControl: true, attributionControl: false }).setView([state.lat, state.lon], 10);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18 }).addTo(state.leafletMap);

  const customIcon = L.divIcon({
    className: "custom-pin",
    html: `<div class="w-3.5 h-3.5 rounded-full bg-sky-400 border border-white"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7]
  });

  state.mapMarker = L.marker([state.lat, state.lon], { icon: customIcon }).addTo(state.leafletMap);
  state.mapMarker.bindPopup(`<b>${state.city}</b>`).openPopup();

  state.hazardCircle = L.circle([state.lat, state.lon], {
    color: "#10b981", fillColor: "#10b981", fillOpacity: 0.1, radius: 10000
  }).addTo(state.leafletMap);
}

function updateMap(lat, lon, cityName, imdColor) {
  if (!state.leafletMap) return;
  state.leafletMap.setView([lat, lon], 11);
  if (state.mapMarker) {
    state.mapMarker.setLatLng([lat, lon]);
    state.mapMarker.setPopupContent(`<b>${cityName}</b>`).openPopup();
  }
  if (state.hazardCircle) {
    state.hazardCircle.setLatLng([lat, lon]);
    const hex = getImdHex(imdColor);
    state.hazardCircle.setStyle({ color: hex, fillColor: hex });
  }
}

function getImdHex(color) {
  switch (color) {
    case "RED": return "#ef4444";
    case "ORANGE": return "#f97316";
    case "YELLOW": return "#eab308";
    case "GREEN":
    default: return "#10b981";
  }
}

// ============================================================
// FAST REFRESH TELEMETRY
// ============================================================
async function refreshTelemetry(lat, lon, city) {
  state.lat = lat;
  state.lon = lon;
  state.city = city;

  document.getElementById("headerLocationName").textContent = city;

  try {
    const res = await fetch(`/api/weather?lat=${lat}&lon=${lon}&city=${encodeURIComponent(city)}`);
    if (!res.ok) throw new Error("Failed to load telemetry");
    const data = await res.json();
    state.telemetry = data;

    bindHeaderAndSidebar(data);
    bindTelemetryView(data);
    renderHourlyChart(data);
    renderDailyForecast(data);
    updateMap(lat, lon, city, data.imd_color);

    if (data.alerts && data.alerts.length > 0) {
      renderDisasterGuide(data.alerts[0].event);
    } else {
      renderDisasterGuide("flood");
    }

  } catch (err) {
    console.error("Telemetry fetch error:", err);
  }
}

function bindHeaderAndSidebar(data) {
  const current = data.telemetry.weather.current || {};
  const cond = data.telemetry.weather.condition_title || "Clear";
  const temp = Math.round(current.temperature_2m ?? 0);
  const imd = data.imd_color || "GREEN";

  document.getElementById("headerLocationName").textContent = data.location.city;
  document.getElementById("headerQuickCondition").textContent = `${temp}°C, ${cond}`;
  document.getElementById("sidebarLiveTemp").textContent = `${temp}°C`;

  // Status Indicator Lights
  const lightDot = document.getElementById("indicatorLightDot");
  const headerDot = document.getElementById("headerDot");
  const sideText = document.getElementById("sidebarImdText");
  const headerText = document.getElementById("headerImdText");

  if (imd === "RED") {
    lightDot.className = "w-2.5 h-2.5 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)] animate-pulse";
    headerDot.className = "w-2 h-2 rounded-full bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.8)] animate-pulse";
    sideText.textContent = "Warning (Red)";
    headerText.textContent = "Red Warning";
  } else if (imd === "ORANGE") {
    lightDot.className = "w-2.5 h-2.5 rounded-full bg-orange-500 shadow-[0_0_8px_rgba(249,115,22,0.8)]";
    headerDot.className = "w-2 h-2 rounded-full bg-orange-500 shadow-[0_0_6px_rgba(249,115,22,0.8)]";
    sideText.textContent = "Alert (Orange)";
    headerText.textContent = "Orange Alert";
  } else if (imd === "YELLOW") {
    lightDot.className = "w-2.5 h-2.5 rounded-full bg-yellow-500 shadow-[0_0_8px_rgba(234,179,8,0.8)]";
    headerDot.className = "w-2 h-2 rounded-full bg-yellow-500 shadow-[0_0_6px_rgba(234,179,8,0.8)]";
    sideText.textContent = "Watch (Yellow)";
    headerText.textContent = "Yellow Watch";
  } else {
    lightDot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]";
    headerDot.className = "w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(34,197,94,0.6)]";
    sideText.textContent = "Normal";
    headerText.textContent = "All Clear";
  }

  // Emergency banner
  const banner = document.getElementById("proactiveAlertBanner");
  if (data.alerts && data.alerts.length > 0) {
    const topAlert = data.alerts[0];
    document.getElementById("bannerAlertMessage").textContent = `${topAlert.message} ${topAlert.recommendation}`;
    banner.classList.remove("hidden");
    if (state.autoSpeak && !state.speechSynthActive) {
      speakAloud(`Weather alert: ${topAlert.message}`);
    }
  } else {
    banner.classList.add("hidden");
  }
}

function bindTelemetryView(data) {
  const current = data.telemetry.weather.current || {};
  const air = data.telemetry.air_quality.current || {};

  document.getElementById("telHeroTemp").textContent = `${Math.round(current.temperature_2m ?? 0)}°C`;
  document.getElementById("telHeroFeels").textContent = `Feels like ${Math.round(current.apparent_temperature ?? current.temperature_2m ?? 0)}°C`;
  document.getElementById("telHeroDesc").textContent = data.telemetry.weather.condition_desc || "Normal conditions";

  document.getElementById("telHeroHumidity").textContent = `${current.relative_humidity_2m ?? '--'}%`;
  document.getElementById("telHeroWind").textContent = `${current.wind_speed_10m ?? '--'} km/h`;
  document.getElementById("telHeroRain").textContent = `${current.precipitation ?? 0} mm`;

  const aqi = Math.round(air.us_aqi || 45);
  document.getElementById("telAqiScore").textContent = aqi > 100 ? `${aqi} (Unhealthy)` : `${aqi} (Good)`;
}

function renderHourlyChart(data) {
  const hourly = data.telemetry.weather.hourly || {};
  const times = hourly.time ? hourly.time.slice(0, 24) : [];
  const temps = hourly.temperature_2m ? hourly.temperature_2m.slice(0, 24) : [];
  const rainProbs = hourly.precipitation_probability ? hourly.precipitation_probability.slice(0, 24) : [];

  const labels = times.map(t => new Date(t).toLocaleTimeString([], { hour: "numeric" }));
  const canvas = document.getElementById("hourlyTrendChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  if (state.hourlyChart) state.hourlyChart.destroy();

  state.hourlyChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Temp (°C)",
          data: temps,
          borderColor: "#38bdf8",
          backgroundColor: "rgba(56, 189, 248, 0.1)",
          fill: true,
          tension: 0.3,
          pointRadius: 1,
          yAxisID: "yTemp"
        },
        {
          label: "Rain (%)",
          data: rainProbs,
          type: "bar",
          backgroundColor: "rgba(148, 163, 184, 0.3)",
          yAxisID: "yRain"
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: "#64748b", font: { size: 9 } } },
        yTemp: { position: "left", grid: { color: "#1f2533" }, ticks: { color: "#38bdf8", font: { size: 9 } } },
        yRain: { position: "right", min: 0, max: 100, grid: { display: false }, ticks: { display: false } }
      }
    }
  });
}

function renderDailyForecast(data) {
  const daily = data.telemetry.weather.daily || {};
  const times = daily.time || [];
  const maxTemps = daily.temperature_2m_max || [];
  const minTemps = daily.temperature_2m_min || [];
  const codes = daily.weather_code || [];

  const container = document.getElementById("sevenDayForecastGrid");
  if (!container) return;
  container.innerHTML = "";

  times.forEach((t, idx) => {
    const dayName = idx === 0 ? "Today" : new Date(t).toLocaleDateString("en-US", { weekday: "short" });
    const code = codes[idx] || 0;
    const iconName = CODE_ICONS[code] || "sun";
    const maxT = maxTemps[idx] !== undefined ? Math.round(maxTemps[idx]) : "--";
    const minT = minTemps[idx] !== undefined ? Math.round(minTemps[idx]) : "--";

    const card = document.createElement("div");
    card.className = "flex flex-col items-center p-2 rounded bg-[#0e1017] text-center text-xs";
    card.innerHTML = `
      <span class="text-slate-400 text-[10px]">${dayName}</span>
      <div class="my-1 text-slate-300"><i data-lucide="${iconName}" class="w-4 h-4"></i></div>
      <div class="font-semibold text-white">${maxT}° <span class="text-slate-500 font-normal">${minT}°</span></div>
    `;
    container.appendChild(card);
  });

  lucide.createIcons();
}

async function loadEmergencyGuides() {
  try {
    const res = await fetch("/api/emergency-guide");
    state.disasterProtocols = await res.json();
  } catch (err) {
    console.warn("Using offline fallback protocols.");
  }
}

function renderDisasterGuide(hazardKey) {
  if (!state.disasterProtocols) return;
  let target = "flood";
  const hk = hazardKey.toLowerCase();
  if (hk.includes("heat")) target = "heatwave";
  else if (hk.includes("cyclone") || hk.includes("wind")) target = "cyclone";
  else if (hk.includes("air") || hk.includes("smog")) target = "air_pollution";

  const guide = state.disasterProtocols[target];
  if (!guide) return;

  const contentArea = document.getElementById("guideContentArea");
  if (!contentArea) return;

  contentArea.innerHTML = `
    <div class="p-3.5 rounded-lg bg-[#0e1017] border border-[#262c3e]">
      <div class="font-semibold text-white text-xs mb-2">${guide.title} — Immediate Steps:</div>
      <ul class="space-y-1.5 text-xs text-slate-300">
        ${guide.immediate_actions.map(act => `<li class="flex items-start gap-1.5"><span class="text-sky-400">•</span> ${act}</li>`).join("")}
      </ul>
    </div>
    <div class="text-xs text-slate-400">Emergency Helpline: <strong class="text-white">${guide.emergency_helpline}</strong></div>
  `;

  document.querySelectorAll(".guide-tab").forEach(tab => {
    if (tab.getAttribute("data-hazard") === target) {
      tab.className = "guide-tab px-3 py-1 text-xs rounded bg-sky-600 text-white font-medium";
    } else {
      tab.className = "guide-tab px-3 py-1 text-xs rounded bg-[#141721] text-slate-400 hover:text-white";
    }
  });
}

// ============================================================
// CHAT ENGINE (CLEAN & NO USER/ROBOT ICONS)
// ============================================================
async function sendChatMessage(queryText) {
  const query = (queryText || document.getElementById("chatInput").value).trim();
  if (!query) return;

  document.getElementById("chatInput").value = "";

  if (state.activeSection !== "section-chat") {
    switchSection("section-chat");
  }

  // Append user message (clean right-aligned bubble, NO human icon)
  appendChatBubble("user", query);

  // Temporary typing indicator
  const typingId = "typing_" + Date.now();
  const typingElem = document.createElement("div");
  typingElem.id = typingId;
  typingElem.className = "text-left text-xs text-slate-500 italic py-1";
  typingElem.textContent = "Thinking...";
  document.getElementById("chatStream").appendChild(typingElem);
  scrollChatToBottom();

  try {
    const payload = {
      message: query,
      latitude: state.lat,
      longitude: state.lon,
      city_name: state.city,
      session_id: state.sessionId,
      history: state.chatHistory.slice(-8),
      api_key: state.apiKey || undefined
    };

    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error("Chat request failed");
    const data = await res.json();

    const elem = document.getElementById(typingId);
    if (elem) elem.remove();

    // Append assistant message (clean left-aligned text, NO robot icon)
    appendChatBubble("assistant", data.response);

    state.chatHistory.push({ role: "user", content: query });
    state.chatHistory.push({ role: "assistant", content: data.response });

    if (state.speechSynthActive || state.autoSpeak) {
      speakAloud(cleanTextForSpeech(data.response));
    }

    if (data.location && (Math.abs(data.location.latitude - state.lat) > 0.05 || Math.abs(data.location.longitude - state.lon) > 0.05 || data.location.city !== state.city)) {
      state.city = data.location.city;
      state.lat = data.location.latitude;
      state.lon = data.location.longitude;
      refreshTelemetry(data.location.latitude, data.location.longitude, data.location.city);
    }

  } catch (err) {
    const elem = document.getElementById(typingId);
    if (elem) elem.remove();
    appendChatBubble("assistant", "Unable to connect to WeatherGPT. Please try again.");
  }
}

function appendChatBubble(role, content) {
  const container = document.getElementById("chatStream");
  const wrapper = document.createElement("div");

  if (role === "user") {
    // Clean user bubble without human avatar
    wrapper.className = "flex justify-end my-2";
    wrapper.innerHTML = `
      <div class="max-w-[80%] bg-[#222738] text-white px-3.5 py-2 rounded-2xl rounded-tr-sm text-sm shadow-sm leading-relaxed">
        ${escapeHtml(content)}
      </div>
    `;
  } else {
    // Clean assistant message without robot avatar
    const formattedHtml = formatMarkdownContent(content);
    wrapper.className = "flex justify-start my-2";
    wrapper.innerHTML = `
      <div class="max-w-[88%] text-left text-slate-200 text-sm leading-relaxed py-1">
        ${formattedHtml}
      </div>
    `;
  }

  container.appendChild(wrapper);
  scrollChatToBottom();
}

function scrollChatToBottom() {
  const container = document.getElementById("chatStream");
  container.scrollTop = container.scrollHeight;
}

function formatMarkdownContent(txt) {
  let html = escapeHtml(txt);
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white font-semibold">$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em class="text-slate-300">$1</em>');
  html = html.replace(/`(.*?)`/g, '<code class="bg-[#141721] px-1 py-0.5 rounded text-sky-400 font-mono text-xs">$1</code>');
  html = html.replace(/\n/g, '<br/>');
  return html;
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function cleanTextForSpeech(str) {
  return str.replace(/[*#`_]/g, "").replace(/\n+/g, ". ");
}

function speakAloud(text) {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.0;
  window.speechSynthesis.speak(utterance);
}

function initSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return;

  const recognition = new SpeechRecognition();
  recognition.lang = "en-IN";
  recognition.continuous = false;

  const btnVoice = document.getElementById("btnVoiceInput");
  const statusElem = document.getElementById("voiceStatusIndicator");

  btnVoice.addEventListener("click", () => {
    if (state.isRecording) recognition.stop();
    else recognition.start();
  });

  recognition.onstart = () => {
    state.isRecording = true;
    btnVoice.classList.add("text-sky-400");
    statusElem.textContent = "Listening...";
  };

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    document.getElementById("chatInput").value = transcript;
    sendChatMessage(transcript);
  };

  recognition.onend = () => {
    state.isRecording = false;
    btnVoice.classList.remove("text-sky-400");
    statusElem.textContent = "";
  };

  recognition.onerror = () => {
    state.isRecording = false;
    statusElem.textContent = "";
  };
}

// ============================================================
// EVENT HANDLERS & SEARCH SETUP
// ============================================================
function initEventHandlers() {
  document.getElementById("chatForm").addEventListener("submit", (e) => {
    e.preventDefault();
    sendChatMessage();
  });

  document.querySelectorAll(".prompt-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const prompt = chip.getAttribute("data-prompt");
      sendChatMessage(prompt);
    });
  });

  document.getElementById("btnHeaderVoiceToggle").addEventListener("click", () => {
    state.speechSynthActive = !state.speechSynthActive;
    const btn = document.getElementById("btnHeaderVoiceToggle");
    if (state.speechSynthActive) {
      btn.className = "p-1.5 rounded text-sky-400";
      speakAloud("Voice feedback enabled.");
    } else {
      btn.className = "p-1.5 rounded text-slate-400 hover:text-white";
      window.speechSynthesis.cancel();
    }
  });

  document.querySelectorAll(".guide-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      renderDisasterGuide(tab.getAttribute("data-hazard"));
    });
  });

  document.getElementById("btnDismissBanner").addEventListener("click", () => {
    document.getElementById("proactiveAlertBanner").classList.add("hidden");
  });
  document.getElementById("btnBannerViewGuide").addEventListener("click", () => {
    switchSection("section-disaster");
  });

  document.querySelectorAll(".city-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      const city = pill.getAttribute("data-city");
      const lat = parseFloat(pill.getAttribute("data-lat"));
      const lon = parseFloat(pill.getAttribute("data-lon"));
      refreshTelemetry(lat, lon, city);
    });
  });

  setupSearchInput("sidebarSearchInput", "sidebarSearchResults");

  document.getElementById("btnSidebarGPS").addEventListener("click", () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      pos => refreshTelemetry(pos.coords.latitude, pos.coords.longitude, "Your Location"),
      () => alert("GPS permission denied.")
    );
  });

  document.getElementById("btnSidebarSimDrill").addEventListener("click", async () => {
    const scenarios = ["flood", "cyclone", "heatwave", "air_pollution"];
    const choice = scenarios[Math.floor(Math.random() * scenarios.length)];
    try {
      const res = await fetch("/api/alerts/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario: choice, city_name: state.city, latitude: state.lat, longitude: state.lon })
      });
      const data = await res.json();
      const banner = document.getElementById("proactiveAlertBanner");
      document.getElementById("bannerAlertMessage").textContent = `[Drill] ${data.guide.title} activated.`;
      banner.classList.remove("hidden");
      renderDisasterGuide(choice);
      updateMap(state.lat, state.lon, state.city, data.imd_color);
      appendChatBubble("assistant", `⚠️ **Drill Activated (${data.imd_color} Level):** ${data.guide.title}. Safety directive: ${data.guide.immediate_actions[0]}`);
      switchSection("section-chat");
    } catch (err) {
      alert("Failed to simulate drill.");
    }
  });

  document.getElementById("btnTestSmsDispatch").addEventListener("click", async () => {
    const inputMsg = document.getElementById("smsInputQuery").value.trim();
    try {
      const res = await fetch("/api/sms-fallback", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ message: inputMsg })
      });
      const data = await res.json();
      document.getElementById("smsOutputDisplay").textContent = data.sms_text;
      document.getElementById("smsCharCount").textContent = `${data.char_count} / 160 chars`;
    } catch (err) {
      document.getElementById("smsOutputDisplay").textContent = "SMS dispatch failed.";
    }
  });
}

function setupSearchInput(inputId, dropdownId) {
  const input = document.getElementById(inputId);
  const dropdown = document.getElementById(dropdownId);
  let debounceTimeout = null;

  input.addEventListener("input", () => {
    clearTimeout(debounceTimeout);
    const q = input.value.trim();
    if (q.length < 2) {
      dropdown.classList.add("hidden");
      return;
    }

    debounceTimeout = setTimeout(async () => {
      try {
        const res = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        const hits = data.results || [];

        if (hits.length === 0) {
          dropdown.innerHTML = `<div class="p-2 text-xs text-slate-500">No locations found</div>`;
          dropdown.classList.remove("hidden");
          return;
        }

        dropdown.innerHTML = hits.map(h => `
          <button class="w-full text-left p-2 hover:bg-[#222738] text-xs flex items-center justify-between text-slate-300" data-lat="${h.latitude}" data-lon="${h.longitude}" data-name="${h.name}">
            <span>${h.display}</span>
          </button>
        `).join("");
        dropdown.classList.remove("hidden");

        dropdown.querySelectorAll("button").forEach(btn => {
          btn.addEventListener("click", () => {
            const lat = parseFloat(btn.getAttribute("data-lat"));
            const lon = parseFloat(btn.getAttribute("data-lon"));
            const name = btn.getAttribute("data-name");
            input.value = name;
            dropdown.classList.add("hidden");
            refreshTelemetry(lat, lon, name);
          });
        });

      } catch (err) {
        console.error("Geocoding error:", err);
      }
    }, 250);
  });

  document.addEventListener("click", e => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.classList.add("hidden");
    }
  });
}

function initSettings() {
  const modal = document.getElementById("settingsModal");
  const keyInput = document.getElementById("cfgOpenAiKey");
  const autoSpeakCheck = document.getElementById("cfgAutoSpeak");

  keyInput.value = state.apiKey;
  autoSpeakCheck.checked = state.autoSpeak;

  document.getElementById("btnOpenSettingsSidebar").addEventListener("click", () => {
    modal.classList.remove("hidden");
    modal.classList.add("flex");
  });

  document.getElementById("btnCloseSettingsModal").addEventListener("click", () => {
    modal.classList.add("hidden");
    modal.classList.remove("flex");
  });

  document.getElementById("btnSaveSettings").addEventListener("click", () => {
    state.apiKey = keyInput.value.trim();
    state.autoSpeak = autoSpeakCheck.checked;
    localStorage.setItem("weathergpt_openai_key", state.apiKey);
    localStorage.setItem("weathergpt_auto_speak", state.autoSpeak);

    modal.classList.add("hidden");
    modal.classList.remove("flex");
  });
}
