from __future__ import annotations

import csv
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# Impact coefficients used only when live provider data is unavailable.
DIESEL_KG_CO2_PER_KWH = 0.7
BASELINE_COST_USD_PER_KWH = 0.28
OPTIMIZED_COST_USD_PER_KWH = 0.19

EFFICIENCY_BASE = 12.0
EFFICIENCY_PRIORITY_MULTIPLIER = 10.0
EFFICIENCY_MAX = 25.0

UNDER_PROVISION_BASE = 10.0
UNDER_PROVISION_PRIORITY_MULTIPLIER = 18.0
UNDER_PROVISION_MAX = 35.0

OVER_WASTE_BASE = 8.0
OVER_WASTE_PRIORITY_MULTIPLIER = 14.0
OVER_WASTE_MAX = 30.0


def _http_get_json(url: str, *, headers: dict[str, str] | None = None, timeout: int = 12) -> dict | list:
    req_headers = {"User-Agent": "Solaris-Agent/1.0"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_text(url: str, *, headers: dict[str, str] | None = None, timeout: int = 12) -> str:
    req_headers = {"User-Agent": "Solaris-Agent/1.0"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
        return out if out == out else None
    except (TypeError, ValueError):
        return None


def _reverse_geo_country(lat: float | None, lon: float | None) -> tuple[str | None, str | None]:
    if lat is None or lon is None:
        return None, None
    try:
        url = (
            "https://nominatim.openstreetmap.org/reverse"
            f"?format=jsonv2&lat={lat}&lon={lon}&zoom=3"
        )
        payload = _http_get_json(url)
        if not isinstance(payload, dict):
            return None, None
        address = payload.get("address", {}) if isinstance(payload.get("address"), dict) else {}
        code = str(address.get("country_code", "")).upper() or None
        name = str(address.get("country", "")).strip() or None
        return code, name
    except Exception:
        return None, None


def _iso2_to_iso3(country_code: str | None) -> str | None:
    if not country_code:
        return None
    try:
        payload = _http_get_json(f"https://restcountries.com/v3.1/alpha/{country_code}")
        if isinstance(payload, list) and payload:
            cca3 = payload[0].get("cca3")
            if isinstance(cca3, str) and len(cca3) == 3:
                return cca3.upper()
    except Exception:
        return None
    return None


def _fetch_carbon_intensity_kg_per_kwh(lat: float | None, lon: float | None, country_code: str | None) -> tuple[float | None, str | None]:
    # 1) ElectricityMaps (live, high quality) when key is available.
    api_key = os.getenv("ELECTRICITYMAPS_API_KEY", "").strip()
    if api_key and lat is not None and lon is not None:
        try:
            url = f"https://api.electricitymap.org/v3/carbon-intensity/latest?lat={lat}&lon={lon}"
            payload = _http_get_json(url, headers={"auth-token": api_key})
            if isinstance(payload, dict):
                g_per_kwh = _safe_float(payload.get("carbonIntensity"))
                if g_per_kwh is not None and g_per_kwh > 0:
                    return round(g_per_kwh / 1000.0, 4), "electricitymaps_live"
        except Exception:
            pass

    # 2) OWID latest country intensity (updated yearly).
    iso3 = _iso2_to_iso3(country_code)
    if iso3:
        try:
            csv_text = _http_get_text("https://ourworldindata.org/grapher/carbon-intensity-electricity.csv")
            rows = csv.DictReader(io.StringIO(csv_text))
            best_year = -1
            best_val: float | None = None
            for row in rows:
                if str(row.get("Code", "")).upper() != iso3:
                    continue
                year = int(float(row.get("Year", "0") or 0))
                val = _safe_float(row.get("Annual CO₂ emissions from electricity"))
                if val is None:
                    continue
                if year >= best_year:
                    best_year = year
                    best_val = val
            if best_val is not None and best_val > 0:
                return round(best_val / 1000.0, 4), f"owid_country_{best_year}"
        except Exception:
            pass

    return None, None


def _fetch_tariff_usd_per_kwh(lat: float | None, lon: float | None, country_name: str | None) -> tuple[float | None, str | None]:
    # 1) OpenEI utility rates (best for US geolocation).
    if lat is not None and lon is not None:
        key = os.getenv("OPENEI_API_KEY", "DEMO_KEY").strip() or "DEMO_KEY"
        try:
            params = urllib.parse.urlencode(
                {
                    "version": "8",
                    "format": "json",
                    "api_key": key,
                    "lat": f"{lat:.6f}",
                    "lon": f"{lon:.6f}",
                }
            )
            payload = _http_get_json(f"https://api.openei.org/utility_rates?{params}")
            if isinstance(payload, dict):
                items = payload.get("items")
                if isinstance(items, list) and items:
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        rate = _safe_float(item.get("residential"))
                        if rate is not None and 0 < rate < 5:
                            return round(rate, 4), "openei_utility_rates"
        except Exception:
            pass

    # 2) GlobalPetrolPrices country page parser (public page data).
    if country_name:
        try:
            candidates = [
                country_name,
                country_name.replace(" ", "-"),
                country_name.replace(" ", "_"),
            ]
            for country_slug in candidates:
                safe_slug = urllib.parse.quote(country_slug, safe="-_")
                url = f"https://www.globalpetrolprices.com/{safe_slug}/electricity_prices/"
                html = _http_get_text(url)
                patterns = [
                    r"([0-9]+(?:\.[0-9]+)?)\s*USD\s*/\s*kWh",
                    r"([0-9]+(?:\.[0-9]+)?)\s*U\.?S\.?\s*Dollar\s*per\s*kWh",
                    r"households[^0-9]{0,40}([0-9]+(?:\.[0-9]+)?)\s*(?:USD|U\.?S\.?\s*Dollar)",
                ]
                for pat in patterns:
                    m = re.search(pat, html, flags=re.IGNORECASE)
                    if not m:
                        continue
                    val = _safe_float(m.group(1))
                    if val is not None and 0 < val < 5:
                        return round(val, 4), "globalpetrolprices_public_page"
        except Exception:
            pass

    return None, None


def compute_impact_metrics(
    *,
    demand_kwh: float,
    households: int,
    priority_score: float,
    confidence_score: float,
    lat: float | None = None,
    lon: float | None = None,
) -> dict:
    annual_kwh = demand_kwh * 365

    country_code, country_name = _reverse_geo_country(lat, lon)
    co2_factor_kg_per_kwh, co2_source = _fetch_carbon_intensity_kg_per_kwh(lat, lon, country_code)
    tariff_usd_per_kwh, tariff_source = _fetch_tariff_usd_per_kwh(lat, lon, country_name)

    co2_avoided_tons: float | None = None
    annual_cost_savings: float | None = None

    if co2_factor_kg_per_kwh is not None and co2_factor_kg_per_kwh > 0:
        co2_avoided_tons = (annual_kwh * co2_factor_kg_per_kwh) / 1000.0

    optimized_cost = _safe_float(os.getenv("SOLARIS_OPTIMIZED_COST_USD_PER_KWH", str(OPTIMIZED_COST_USD_PER_KWH)))
    if optimized_cost is None:
        optimized_cost = OPTIMIZED_COST_USD_PER_KWH
    if tariff_usd_per_kwh is not None and tariff_usd_per_kwh > 0 and tariff_usd_per_kwh > optimized_cost:
        annual_cost_savings = annual_kwh * (tariff_usd_per_kwh - optimized_cost)

    efficiency_gain = round(min(EFFICIENCY_MAX, EFFICIENCY_BASE + (priority_score * EFFICIENCY_PRIORITY_MULTIPLIER)), 2)
    under_risk_reduction = round(
        min(UNDER_PROVISION_MAX, UNDER_PROVISION_BASE + (priority_score * UNDER_PROVISION_PRIORITY_MULTIPLIER)), 2
    )
    over_waste_reduction = round(min(OVER_WASTE_MAX, OVER_WASTE_BASE + (priority_score * OVER_WASTE_PRIORITY_MULTIPLIER)), 2)

    return {
        "estimated_efficiency_gain_pct": efficiency_gain,
        "under_provisioning_risk_reduction_pct": under_risk_reduction,
        "over_provisioning_waste_reduction_pct": over_waste_reduction,
        "households_served_estimate": households,
        "confidence_score": round(confidence_score, 2),
        "confidence_band": "high" if confidence_score >= 0.8 else ("medium" if confidence_score >= 0.6 else "low"),
        "assumptions": [
            "Impact values are computed from live external data sources when available.",
            f"Optimized solar LCOE baseline: {optimized_cost} USD/kWh.",
        ],
        "impact_data_sources": {
            "country_code": country_code,
            "country_name": country_name,
            "carbon_intensity_source": co2_source,
            "tariff_source": tariff_source,
            "carbon_factor_kg_per_kwh": co2_factor_kg_per_kwh,
            "tariff_usd_per_kwh": tariff_usd_per_kwh,
        },
    }

    if co2_avoided_tons is not None and co2_avoided_tons > 0:
        result["co2_avoided_tons_estimate"] = round(co2_avoided_tons, 2)
    if annual_cost_savings is not None and annual_cost_savings > 0:
        result["annual_cost_savings_usd_estimate"] = round(annual_cost_savings, 2)

    if co2_avoided_tons is None:
        result["assumptions"].append(
            f"Carbon factor unavailable from live APIs; fallback constant would be {DIESEL_KG_CO2_PER_KWH} kgCO2/kWh."
        )
    if annual_cost_savings is None:
        result["assumptions"].append(
            f"Tariff unavailable from live APIs; fallback baseline would be {BASELINE_COST_USD_PER_KWH} USD/kWh."
        )

    return result
