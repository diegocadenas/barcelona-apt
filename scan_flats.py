#!/usr/bin/env python3
"""Scrape Habitatge Jove flats and rank by proximity to school."""

from __future__ import annotations

import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
REPORTS_DIR = ROOT / "reports"
GEOCODE_CACHE_PATH = ROOT / "geocode_cache.json"
BASE = "https://www.habitatgejove.com/webv2c/en/"

MONTH_LABELS = {
    0: "Available now",
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}

MONTH_ORDER = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5, "JUNE": 6,
    "JULY": 7, "JULIO": 7, "AUGUST": 8, "AGOSTO": 8, "SEPTEMBER": 9, "SEPTIEMBRE": 9,
    "OCTOBER": 10, "OCTUBRE": 10, "NOVEMBER": 11, "DECEMBER": 12,
}


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "barcelona-apt/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("latin-1", errors="replace")


def parse_listings() -> list[dict]:
    flats: list[dict] = []
    for page in range(1, 6):
        url = f"{BASE}pisos.asp" if page == 1 else f"{BASE}pisos.asp?page={page}"
        html = fetch(url)
        blocks = re.findall(r"<a href='piso\.asp\?CODI=(\d+)'>(.*?)</a></div>", html, re.DOTALL)
        for code, block in blocks:
            price = re.search(r"class='price'>(\d+)", block)
            location = re.search(r"class='location'>(.*?)</div>", block)
            zone = re.search(r"class='zone'>(.*?)</div>", block)
            avail = re.search(r"Availability:</strong>\s*(.*?)</div>", block)
            props = re.findall(r"class='text'>(\d+)", block)
            if len(props) < 3:
                continue
            flats.append({
                "code": code,
                "price": int(price.group(1)) if price else 0,
                "street": clean_html(location.group(1) if location else ""),
                "zone": clean_html(zone.group(1) if zone else ""),
                "availability_raw": clean_html(avail.group(1) if avail else ""),
                "m2": int(props[0]),
                "rooms": int(props[1]),
                "baths": int(props[2]),
                "url": f"{BASE}piso.asp?CODI={code}",
            })
    return flats


def clean_html(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("&nbsp;", " ")).strip()


def fetch_detail(code: str) -> dict:
    html = fetch(f"{BASE}piso.asp?CODI={code}")
    subway = re.search(r"Nearest subway:</strong>\s*(.*?)</p>", html, re.S)
    rent = re.search(r"Rental price:</strong>\s*(\d+)", html)
    supplies = re.search(r"Providing supplies:</strong>\s*(\d+)", html)
    avail = re.search(r"Availability:</strong>\s*(.*?)</", html)
    return {
        "subway": clean_html(subway.group(1)) if subway else "",
        "rent": int(rent.group(1)) if rent else None,
        "supplies": int(supplies.group(1)) if supplies else None,
        "availability_raw": clean_html(avail.group(1)) if avail else "",
    }


def parse_availability(raw: str) -> tuple[str | None, int | None, int | None]:
    upper = raw.upper()
    if "AVAILABLE" in upper or "DISPONIBLE" in upper:
        return ("Available now", 0, (0, 0))

    day_match = re.search(r"(\d{1,2})", raw)
    day = int(day_match.group(1)) if day_match else None

    month = None
    for name, num in MONTH_ORDER.items():
        if name in upper:
            month = num
            break

    label = None
    if day is not None and month is not None:
        label = f"{day} {MONTH_LABELS[month]}"
    elif raw.strip():
        label = re.sub(r"^Entry\s+", "", raw.strip(), flags=re.I)
        for name, num in MONTH_ORDER.items():
            if name in upper and num in MONTH_LABELS:
                label = re.sub(rf"\b{name}\b", MONTH_LABELS[num], label, flags=re.I)
                break
    sort_key = (month if month is not None else 99, day if day is not None else 99)
    return (label, month, sort_key)


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    x = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.asin(math.sqrt(x))


def geocode(query: str) -> tuple[float, float] | None:
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "limit": 1, "countrycodes": "es"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "barcelona-apt/1.0"})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=30).read())
    except OSError:
        return None
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])


def load_geocode_cache() -> dict:
    if GEOCODE_CACHE_PATH.exists():
        with GEOCODE_CACHE_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_geocode_cache(cache: dict) -> None:
    with GEOCODE_CACHE_PATH.open("w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def geocode_flat(flat: dict, overrides: dict, cache: dict) -> tuple[float, float] | None:
    code = flat["code"]
    if code in cache:
        entry = cache[code]
        return entry["lat"], entry["lon"]

    if code in overrides:
        query = overrides[code]
    else:
        zone_clean = flat["zone"].replace(" - BARCELONA", "").strip()
        query = f"{flat['street']}, {zone_clean}, Barcelona, Spain"

    coords = geocode(query)
    time.sleep(1.1)
    if not coords and code not in overrides:
        coords = geocode(f"{flat['street']}, Barcelona, Spain")
        time.sleep(1.1)

    if coords:
        cache[code] = {"lat": coords[0], "lon": coords[1], "query": query}
    return coords


def should_exclude(flat: dict, config: dict) -> bool:
    zone = flat["zone"].upper()
    if any(ex in zone for ex in config["exclude_zones"]):
        return True

    _, month, _ = parse_availability(flat.get("availability_label") or flat["availability_raw"])
    if month in config.get("exclude_availability_months", []):
        return True

    if flat.get("walk_min") is not None and flat["walk_min"] > config["max_walk_minutes"]:
        return True

    return False


def priority_rank(flat: dict) -> tuple:
    zone = flat["zone"].upper()
    if "EIXAMPLE" in zone:
        tier = 0
    elif "GRÀCIA" in zone or "GRACIA" in zone or "SANT GERVASI" in zone:
        tier = 1
    else:
        tier = 2
    return (tier, flat.get("walk_min") or 999, flat.get("availability_sort") or (99, 99))


def build_json_payload(flats: list[dict], config: dict, generated_at: datetime) -> dict:
    def serialize(flat: dict) -> dict:
        zone = flat["zone"].replace(" - BARCELONA", "")
        tier = 0 if "EIXAMPLE" in flat["zone"].upper() else (
            1 if any(x in flat["zone"].upper() for x in ("GRÀCIA", "GRACIA", "SANT GERVASI")) else 2
        )
        tier_labels = {0: "Eixample", 1: "Gràcia area", 2: "Other"}
        return {
            "code": flat["code"],
            "url": flat["url"],
            "street": flat["street"],
            "zone": zone,
            "tier": tier,
            "tier_label": tier_labels[tier],
            "rooms": flat["rooms"],
            "m2": flat["m2"],
            "baths": flat["baths"],
            "rent": flat.get("rent"),
            "supplies": flat.get("supplies"),
            "total": flat.get("total"),
            "availability": flat.get("availability_label") or flat.get("availability_raw"),
            "availability_month": flat.get("availability_month"),
            "availability_month_label": MONTH_LABELS.get(
                flat.get("availability_month"), "Unknown"
            ) if flat.get("availability_month") is not None else "Unknown",
            "walk_min": round(flat["walk_min"]) if flat.get("walk_min") is not None else None,
            "dist_km": flat.get("dist_km"),
            "lat": flat.get("lat"),
            "lon": flat.get("lon"),
            "subway": flat.get("subway", ""),
        }

    sorted_flats = sorted(flats, key=priority_rank)
    month_counts: dict[int, int] = {}
    for flat in sorted_flats:
        month = flat.get("availability_month")
        if month is not None:
            month_counts[month] = month_counts.get(month, 0) + 1

    available_months = [
        {
            "value": month,
            "label": MONTH_LABELS.get(month, "Unknown"),
            "count": count,
        }
        for month, count in sorted(month_counts.items(), key=lambda x: (0 if x[0] == 0 else 1, x[0]))
    ]

    return {
        "generated_at": generated_at.isoformat(),
        "generated_label": generated_at.strftime("%d %b %Y, %H:%M"),
        "school_address": config["school_address"],
        "criteria": {
            "min_rooms": config["min_rooms"],
            "max_walk_minutes": config["max_walk_minutes"],
            "exclude_zones": config["exclude_zones"],
            "exclude_availability_months": config.get("exclude_availability_months", []),
        },
        "count": len(sorted_flats),
        "available_months": available_months,
        "school": {
            "address": config["school_address"],
            "lat": config["school_coords"][0],
            "lon": config["school_coords"][1],
        },
        "flats": [serialize(f) for f in sorted_flats],
    }


def build_report(flats: list[dict], generated_at: datetime) -> str:
    lines = [
        f"# Barcelona apartment scan — {generated_at.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"School: {load_config()['school_address']}",
        f"Criteria: {load_config()['min_rooms']}+ rooms, ≤{load_config()['max_walk_minutes']} min walk, "
        f"exclude {', '.join(load_config()['exclude_zones'])}, no October availability",
        "",
    ]

    if not flats:
        lines.append("_No matching flats today._")
        return "\n".join(lines)

    def row(f: dict, idx: int) -> str:
        total = f.get("total") or "?"
        walk = f"~{f['walk_min']:.0f} min" if f.get("walk_min") is not None else "?"
        return (
            f"| {idx} | [{f['code']}]({f['url']}) | {f['street']} | {f['zone'].replace(' - BARCELONA', '')} | "
            f"{f['rooms']} | €{total} | {f.get('availability_label', '?')} | {walk} | {f.get('subway', '')} |"
        )

    sorted_flats = sorted(flats, key=priority_rank)

    lines += [
        "## Flats by location",
        "",
        "| # | Code | Street | Area | Rooms | Total/mo | Available | Walk | Metro |",
        "|---|------|--------|------|-------|----------|-----------|------|-------|",
    ]
    for idx, flat in enumerate(sorted_flats, 1):
        lines.append(row(flat, idx))

    return "\n".join(lines)


def main() -> int:
    config = load_config()
    school = tuple(config["school_coords"])
    overrides = config.get("geocode_overrides", {})

    listings = parse_listings()
    candidates = [f for f in listings if f["rooms"] >= config["min_rooms"]]

    geocode_cache = load_geocode_cache()
    enriched: list[dict] = []
    for flat in candidates:
        detail = fetch_detail(flat["code"])
        flat.update(detail)
        flat["availability_label"], month, sort_key = parse_availability(
            detail["availability_raw"] or flat["availability_raw"]
        )
        flat["availability_sort"] = sort_key
        flat["availability_month"] = month
        if flat["rent"] is not None and flat["supplies"] is not None:
            flat["total"] = flat["rent"] + flat["supplies"]
        else:
            flat["total"] = flat["price"]

        coords = geocode_flat(flat, overrides, geocode_cache)
        if coords:
            flat["lat"], flat["lon"] = coords
            km = haversine_km(school, coords)
            flat["walk_min"] = km * 12
            flat["dist_km"] = round(km, 2)
        else:
            flat["lat"] = flat["lon"] = None
            flat["walk_min"] = None
            flat["dist_km"] = None

        if not should_exclude(flat, config):
            enriched.append(flat)

    save_geocode_cache(geocode_cache)
    enriched.sort(key=priority_rank)

    generated_at = datetime.now()
    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / f"{generated_at.strftime('%Y-%m-%d-%H')}.md"
    latest_path = REPORTS_DIR / "latest.md"

    report = build_report(enriched, generated_at)
    payload = build_json_payload(enriched, config, generated_at)

    report_path.write_text(report, encoding="utf-8")
    latest_path.write_text(report, encoding="utf-8")
    json_path = REPORTS_DIR / "latest.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(report)
    print(f"\nSaved: {report_path}")
    print(f"JSON:  {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
