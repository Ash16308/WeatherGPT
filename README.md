# WeatherGPT
This is the first project of Team Cryptic for SIH 2026

The idea is:

**Weather API JSON → Normalize data → Rule/AI interpretation → Layman-friendly response**

Here is a clean TypeScript implementation you can directly adapt to your React app.

### 1. Define a common weather model

```ts
// types/weather.ts

export interface WeatherData {
  location: string;
  temperature: number;
  feelsLike: number;
  condition: string;
  humidity: number;
  windSpeed: number;
  rainProbability: number;
  uvIndex: number;
}

export interface ForecastDay {
  day: string;
  high: number;
  low: number;
  condition: string;
  rainProbability: number;
}
```

### 2. Convert API response into your common format

This is useful because OpenWeather, IMD, WeatherAPI, etc. all return data in different formats.

```ts
// services/weatherNormalizer.ts

import { WeatherData } from "../types/weather";

export function normalizeWeatherApiResponse(apiData: any): WeatherData {
  return {
    location: apiData.name,
    temperature: Math.round(apiData.main.temp),
    feelsLike: Math.round(apiData.main.feels_like),
    condition: apiData.weather?.[0]?.main ?? "Unknown",
    humidity: apiData.main.humidity,
    windSpeed: Math.round(apiData.wind.speed * 3.6), // m/s → km/h
    rainProbability: Math.round((apiData.rainProbability ?? 0) * 100),
    uvIndex: apiData.uvi ?? 0,
  };
}
```

Now your application doesn't care whether the data came from OpenWeather or another provider.

---

# 3. The "Layman's Terms" Intelligence Layer

This is the part you can explain to the judge.

```ts
// services/weatherInterpreter.ts

import { WeatherData } from "../types/weather";

export function explainWeather(weather: WeatherData): string {
  const parts: string[] = [];

  // Temperature
  if (weather.temperature >= 35) {
    parts.push("It's very hot outside");
  } else if (weather.temperature >= 30) {
    parts.push("It's quite warm outside");
  } else if (weather.temperature >= 24) {
    parts.push("The temperature is comfortable");
  } else if (weather.temperature >= 18) {
    parts.push("It's a little cool outside");
  } else {
    parts.push("It's cold outside");
  }

  // Rain
  if (weather.rainProbability >= 70) {
    parts.push("there is a high chance of rain");
  } else if (weather.rainProbability >= 40) {
    parts.push("rain is quite possible");
  } else if (weather.rainProbability >= 20) {
    parts.push("there is a small chance of rain");
  } else {
    parts.push("rain is unlikely");
  }

  // Humidity
  if (weather.humidity >= 80) {
    parts.push("and it will feel quite humid");
  } else if (weather.humidity >= 60) {
    parts.push("with moderate humidity");
  }

  return parts.join(", ") + ".";
}
```

For example, raw data like:

```json
{
  "temperature": 31,
  "humidity": 78,
  "rainProbability": 65
}
```

becomes:

> **"It's quite warm outside, rain is quite possible, and it will feel quite humid."**

That's your **weather → human language** layer.

---

# 4. Make it answer actual questions

You can build another layer on top of that.

```ts
// services/weatherGPT.ts

import { WeatherData } from "../types/weather";

export function generateWeatherGPTResponse(
  question: string,
  weather: WeatherData
): string {

  const q = question.toLowerCase();

  // Today's weather
  if (
    q.includes("weather today") ||
    q.includes("weather now") ||
    q.includes("temperature today")
  ) {
    return `Today in ${weather.location}, it's ${weather.temperature}°C and ${weather.condition.toLowerCase()}. It feels like ${weather.feelsLike}°C, with ${weather.humidity}% humidity and a ${weather.rainProbability}% chance of rain.`;
  }

  // Clothing
  if (
    q.includes("what should i wear") ||
    q.includes("what to wear") ||
    q.includes("clothes")
  ) {
    if (weather.temperature >= 32) {
      return `It's quite hot today at ${weather.temperature}°C. Light, breathable clothing would be comfortable.`;
    }

    if (weather.rainProbability >= 50) {
      return `The temperature is around ${weather.temperature}°C and rain is possible. Light clothing along with something to protect you from rain would be a good choice.`;
    }

    return `The weather is fairly comfortable at ${weather.temperature}°C. Light, comfortable clothing should work well today.`;
  }

  // Umbrella
  if (
    q.includes("umbrella") ||
    q.includes("will it rain")
  ) {
    if (weather.rainProbability >= 60) {
      return `There's a ${weather.rainProbability}% chance of rain. Carrying an umbrella would be a good idea.`;
    }

    if (weather.rainProbability >= 30) {
      return `There's a ${weather.rainProbability}% chance of rain. You may want to carry an umbrella, especially if you're going out for a long time.`;
    }

    return `Rain is unlikely, with only a ${weather.rainProbability}% chance. You probably won't need an umbrella.`;
  }

  // Running / outdoor activity
  if (
    q.includes("run") ||
    q.includes("running") ||
    q.includes("outdoor")
  ) {
    if (
      weather.temperature <= 28 &&
      weather.rainProbability < 30
    ) {
      return `The conditions look good for outdoor activity. It's around ${weather.temperature}°C with a low chance of rain.`;
    }

    if (weather.rainProbability >= 50) {
      return `Rain is fairly likely at ${weather.rainProbability}%, so outdoor activities may be better planned for another time.`;
    }

    if (weather.temperature >= 32) {
      return `It's quite warm at ${weather.temperature}°C. If you're exercising outdoors, a cooler part of the day would be more comfortable.`;
    }

    return `Outdoor activity is possible, but keep an eye on the ${weather.rainProbability}% chance of rain and the current temperature.`;
  }

  // General explanation
  if (
    q.includes("explain") ||
    q.includes("simple") ||
    q.includes("layman")
  ) {
    return explainWeather(weather);
  }

  // Fallback
  return `I can help you understand the temperature, rain chances, clothing recommendations, outdoor activities, forecasts, and weather alerts.`;
}

function explainWeather(weather: WeatherData): string {
  const temperature =
    weather.temperature >= 32
      ? "It's quite hot"
      : weather.temperature >= 24
      ? "The temperature is comfortable"
      : "It's relatively cool";

  const rain =
    weather.rainProbability >= 60
      ? "rain is likely"
      : weather.rainProbability >= 30
      ? "you may get some rain"
      : "rain is unlikely";

  const humidity =
    weather.humidity >= 75
      ? "and it will feel humid"
      : "with manageable humidity";

  return `${temperature at ${weather.temperature}°C, ${rain}, ${humidity}.`;
}
```

---

# 5. Your complete architecture

For your presentation, show the judge this:

```text
             REAL WEATHER API
                    │
                    ▼
          ┌───────────────────┐
          │ API Adapter        │
          │ / API Connector    │
          └─────────┬─────────┘
                    │
                    ▼
          ┌───────────────────┐
          │ Data Normalizer   │
          │                   │
          │ API JSON →        │
          │ WeatherData       │
          └─────────┬─────────┘
                    │
                    ▼
          ┌───────────────────┐
          │ Weather           │
          │ Intelligence      │
          │ Layer             │
          └─────────┬─────────┘
                    │
          ┌─────────┴──────────┐
          ▼                    ▼
   Rule-based logic        LLM Layer
          │                    │
          └─────────┬──────────┘
                    ▼
          ┌───────────────────┐
          │ Layman-friendly   │
          │ Response          │
          └─────────┬─────────┘
                    ▼
             WeatherGPT Chat
```

### The important distinction

Don't tell the judge:

> "Our AI converts API data into English."

Instead say:

> **"We normalize heterogeneous weather API data into a common weather model, derive contextual insights from that structured data, and then use a conversational layer to explain those insights in natural language."**

That sounds much more technically credible.

---

## If you later add an actual LLM

The architecture doesn't need to change much:

```ts
export async function generateWeatherGPTResponse(
  question: string,
  weather: WeatherData
) {

  const context = `
Location: ${weather.location}
Temperature: ${weather.temperature}°C
Feels like: ${weather.feelsLike}°C
Condition: ${weather.condition}
Humidity: ${weather.humidity}%
Wind: ${weather.windSpeed} km/h
Rain probability: ${weather.rainProbability}%
UV Index: ${weather.uvIndex}
`;

  // Replace this section with your chosen LLM API.
  // IMPORTANT:
  // The LLM should explain the supplied weather data,
  // not invent its own weather values.

  const prompt = `
You are WeatherGPT, a friendly weather assistant.

Use ONLY the supplied weather information.

Explain it in simple language that a normal person
can understand.

Weather data:
${context}

User question:
${question}
`;

  // const response = await callLLM(prompt);
  // return response;

  return explainWeather(weather);
}
```

This gives you a very good **future-ready architecture**:

> **API provides facts → intelligence layer derives meaning → LLM communicates the meaning.**

And that's probably the strongest technical explanation of your project's "different" layer for an SIH judge.
