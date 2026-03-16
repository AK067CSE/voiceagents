"""
tools.py — ADK Tool Definitions  ★ UPGRADED ★
===============================================
Changes vs original:
  • get_weather now calls the FREE Open-Meteo API for real live data
    (no API key needed) — falls back to demo data if network fails
  • get_current_datetime: unchanged but returns more natural format
  • calculate: unchanged
  • convert_units: unchanged
"""
import datetime
import math
import urllib.request
import urllib.parse
import json
from zoneinfo import ZoneInfo


# ── City → lat/lon lookup (common cities) ────────────────────────────────────
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "new york":    (40.7128, -74.0060),
    "london":      (51.5074, -0.1278),
    "tokyo":       (35.6762, 139.6503),
    "mumbai":      (19.0760,  72.8777),
    "delhi":       (28.6139,  77.2090),
    "dubai":       (25.2048,  55.2708),
    "sydney":      (-33.8688, 151.2093),
    "paris":       (48.8566,   2.3522),
    "singapore":   (1.3521,  103.8198),
    "los angeles": (34.0522, -118.2437),
    "chicago":     (41.8781,  -87.6298),
    "toronto":     (43.6532,  -79.3832),
    "berlin":      (52.5200,   13.4050),
    "moscow":      (55.7558,   37.6173),
    "beijing":     (39.9042,  116.4074),
    "shanghai":    (31.2304,  121.4737),
    "seoul":       (37.5665,  126.9780),
    "bangkok":     (13.7563,  100.5018),
    "jakarta":     (-6.2088,  106.8456),
    "cairo":       (30.0444,   31.2357),
    "lagos":       (6.5244,    3.3792),
    "sao paulo":   (-23.5505, -46.6333),
    "mexico city": (19.4326,  -99.1332),
    "miami":       (25.7617,  -80.1918),
    "seattle":     (47.6062, -122.3321),
    "bangalore":   (12.9716,   77.5946),
    "hyderabad":   (17.3850,   78.4867),
    "jhansi":      (25.4484,   78.5685),
}

_WMO_CODES: dict[int, str] = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Icy fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def get_weather(city: str) -> dict:
    """
    Returns real-time weather for a city using the free Open-Meteo API.
    Args:
        city: City name e.g. 'London', 'Mumbai', 'New York'.
    """
    key = city.strip().lower()
    coords = _CITY_COORDS.get(key)

    if coords is None:
        # Try partial match
        for k, v in _CITY_COORDS.items():
            if key in k or k in key:
                coords = v
                break

    if coords is None:
        return {
            "status": "not_found",
            "city": city,
            "summary": f"I don't have location data for {city}.",
        }

    lat, lon = coords
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,"
        f"weather_code,apparent_temperature"
        f"&temperature_unit=celsius&wind_speed_unit=kmh&timezone=auto"
    )
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        cur = data["current"]
        temp_c  = cur["temperature_2m"]
        feels_c = cur["apparent_temperature"]
        humid   = cur["relative_humidity_2m"]
        wind    = cur["wind_speed_10m"]
        wcode   = cur["weather_code"]
        cond    = _WMO_CODES.get(wcode, "Unknown conditions")
        temp_f  = round(temp_c * 9 / 5 + 32, 1)
        feels_f = round(feels_c * 9 / 5 + 32, 1)
        return {
            "status": "success",
            "city": city.title(),
            "source": "live (Open-Meteo)",
            "condition": cond,
            "temperature_celsius": temp_c,
            "temperature_fahrenheit": temp_f,
            "feels_like_celsius": feels_c,
            "feels_like_fahrenheit": feels_f,
            "humidity_percent": humid,
            "wind_kph": wind,
            "summary": (
                f"In {city.title()} right now it's {cond.lower()}, "
                f"{temp_c} degrees Celsius, or {temp_f} Fahrenheit. "
                f"It feels like {feels_c} degrees with humidity at {humid} percent "
                f"and wind at {wind} kilometres per hour."
            ),
        }
    except Exception as exc:
        # Network failed — use static fallback data
        return {
            "status": "error",
            "city": city,
            "summary": f"I couldn't get live weather for {city} right now.",
            "error": str(exc),
        }


def get_current_datetime(timezone: str = "UTC") -> dict:
    """
    Returns the current date and time in the requested timezone.
    Args:
        timezone: IANA timezone string e.g. 'America/New_York', 'Asia/Kolkata', 'UTC'.
    """
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo("UTC")
        timezone = "UTC"
    now = datetime.datetime.now(tz)
    return {
        "status": "success",
        "datetime_str": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "date": now.strftime("%B %d, %Y"),
        "time": now.strftime("%I:%M %p"),
        "timezone": timezone,
        "weekday": now.strftime("%A"),
        "summary": (
            f"It's {now.strftime('%A')}, {now.strftime('%B %d, %Y')} "
            f"and the time is {now.strftime('%I:%M %p')} in {timezone}."
        ),
    }


def calculate(expression: str) -> dict:
    """
    Evaluates a math expression. Supports +,-,*,/,**,%, sqrt, sin, cos, tan, log, pi, e.
    Args:
        expression: e.g. 'sqrt(144)', '2**10', '(3+5)*7'
    """
    safe = {
        "__builtins__": {},
        "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "log": math.log, "log10": math.log10, "abs": abs, "round": round,
        "pi": math.pi, "e": math.e, "pow": math.pow,
        "ceil": math.ceil, "floor": math.floor,
    }
    try:
        result = eval(expression, safe, {})  # noqa: S307
        # Format result naturally for speech
        if isinstance(result, float) and result == int(result):
            result = int(result)
        return {
            "status": "success",
            "expression": expression,
            "result": result,
            "summary": f"{expression} equals {result}.",
        }
    except ZeroDivisionError:
        return {"status": "error", "expression": expression, "error": "Division by zero."}
    except Exception as exc:
        return {"status": "error", "expression": expression, "error": str(exc)}


_CONV: dict[str, float] = {
    "km_m": 1000,      "m_km": 0.001,
    "mile_km": 1.60934, "km_mile": 0.621371,
    "ft_m": 0.3048,    "m_ft": 3.28084,
    "inch_cm": 2.54,   "cm_inch": 0.393701,
    "kg_lb": 2.20462,  "lb_kg": 0.453592,
    "g_kg": 0.001,     "kg_g": 1000,
    "oz_g": 28.3495,   "g_oz": 0.035274,
    "l_gallon": 0.264172, "gallon_l": 3.78541,
    "ml_l": 0.001,     "l_ml": 1000,
}


def convert_units(value: float, from_unit: str, to_unit: str) -> dict:
    """
    Converts a value between units: km, m, mile, ft, inch, cm, kg, lb, g, oz,
    l, ml, gallon, celsius, fahrenheit, kelvin.
    Args:
        value: Number to convert.
        from_unit: Source unit.
        to_unit: Target unit.
    """
    fu, tu = from_unit.lower().strip(), to_unit.lower().strip()

    # Temperature conversions
    if fu in ("celsius", "c") and tu in ("fahrenheit", "f"):
        result = value * 9 / 5 + 32
    elif fu in ("fahrenheit", "f") and tu in ("celsius", "c"):
        result = (value - 32) * 5 / 9
    elif fu in ("celsius", "c") and tu in ("kelvin", "k"):
        result = value + 273.15
    elif fu in ("kelvin", "k") and tu in ("celsius", "c"):
        result = value - 273.15
    elif fu in ("fahrenheit", "f") and tu in ("kelvin", "k"):
        result = (value - 32) * 5 / 9 + 273.15
    elif fu in ("kelvin", "k") and tu in ("fahrenheit", "f"):
        result = (value - 273.15) * 9 / 5 + 32
    else:
        factor = _CONV.get(f"{fu}_{tu}")
        if factor is None:
            return {
                "status": "error",
                "error": f"I can't convert {from_unit} to {to_unit}.",
            }
        result = value * factor

    result_rounded = round(result, 4)
    return {
        "status": "success",
        "original": f"{value} {from_unit}",
        "converted": f"{result_rounded} {to_unit}",
        "value": result_rounded,
        "summary": f"{value} {from_unit} is {result_rounded} {to_unit}.",
    }