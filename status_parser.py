import requests
import re
import json
import os
import time
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COUNTRY_MAP_FILE = os.path.join(BASE_DIR, "country_map.json")
COUNTRY_MAP_TTL = 24 * 60 * 60  # 24 hours

_map_lock = threading.Lock()

API_SOURCES = [
    {
        "name": "Yapily Platform",
        "components_url": "https://status.yapily.com/api/v2/components.json",
        "summary_url": "https://status.yapily.com/api/v2/summary.json",
        "page_url": "https://status.yapily.com/",
        "has_countries": False
    },
    {
        "name": "Yapily Institutions",
        "components_url": "https://status-institutions.yapily.com/api/v2/components.json",
        "summary_url": "https://status-institutions.yapily.com/api/v2/summary.json",
        "page_url": "https://status-institutions.yapily.com/",
        "has_countries": True
    }
]

# Statuses that are NOT operational (🔴 red and 🟡 yellow)
PROBLEM_STATUSES = {
    "major_outage",        # 🔴 Red
    "partial_outage",      # 🟡 Yellow
    "degraded_performance" # 🟡 Yellow
}

STATUS_EMOJI = {
    "major_outage": "🔴",
    "partial_outage": "🟡",
    "degraded_performance": "🟡",
    "under_maintenance": "🔧",
    "operational": "🟢"
}

STATUS_LABEL = {
    "major_outage": "Major Outage",
    "partial_outage": "Partial Outage",
    "degraded_performance": "Degraded Performance",
    "under_maintenance": "Under Maintenance",
    "operational": "Operational"
}

IMPACT_EMOJI = {
    "critical": "🔴",
    "major": "🔴",
    "minor": "🟡",
    "none": "⚪"
}

COUNTRY_FLAGS = {
    "Austria": "🇦🇹",
    "Belgium": "🇧🇪",
    "Denmark": "🇩🇰",
    "Estonia": "🇪🇪",
    "Finland": "🇫🇮",
    "France": "🇫🇷",
    "Germany": "🇩🇪",
    "Iceland": "🇮🇸",
    "Ireland": "🇮🇪",
    "Italy": "🇮🇹",
    "Latvia": "🇱🇻",
    "Lithuania": "🇱🇹",
    "Netherlands": "🇳🇱",
    "Norway": "🇳🇴",
    "Poland": "🇵🇱",
    "Portugal": "🇵🇹",
    "Spain": "🇪🇸",
    "Sweden": "🇸🇪",
    "United Kingdom": "🇬🇧"
}


# ─── Country mapping ─────────────────────────────────────────────────

def _load_country_map_from_file():
    with _map_lock:
        if os.path.exists(COUNTRY_MAP_FILE):
            try:
                with open(COUNTRY_MAP_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
    return None


def _save_country_map(country_map):
    with _map_lock:
        with open(COUNTRY_MAP_FILE, "w") as f:
            json.dump(country_map, f, indent=2, ensure_ascii=False)


def _fetch_country_map_from_html():
    """Parse the Yapily Institutions status page HTML to extract bank→country mapping."""
    cached = _load_country_map_from_file()
    try:
        r = requests.get("https://status-institutions.yapily.com/", timeout=30)
        r.raise_for_status()
        html = r.text

        # Extract RSC (React Server Components) data from Next.js page
        chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.+?)"\]\)', html, re.DOTALL)
        full_text = "".join(chunks)
        full_text = full_text.replace('\\"', '"').replace('\\\\', '\\')

        # Find group structures: "group":{"components":[...],...,"name":"CountryName"}
        group_pattern = re.finditer(
            r'"group":\{"components":\[(.*?)\],"description":"[^"]*","display_aggregated_uptime":[^,]+,"hidden":[^,]+,"id":"[^"]+","name":"([^"]+)"\}',
            full_text
        )

        country_map = {}
        for m in group_pattern:
            country = m.group(2)
            comps_str = m.group(1)
            comp_ids = re.findall(r'"component_id":"([^"]+)"[^}]*"name":"([^"]+)"', comps_str)
            for cid, cname in comp_ids:
                country_map[cid] = {"country": country, "name": cname}

        if not country_map:
            print("⚠️ HTML parse returned empty country map — HTML structure may have changed, keeping stale cache")
            return cached or {}

        if cached and len(country_map) < len(cached) * 0.8:
            print(f"⚠️ Country map shrank significantly: {len(cached)} → {len(country_map)} entries (HTML structure may have changed)")

        _save_country_map(country_map)
        print(f"✅ Country map updated: {len(country_map)} banks across {len(set(v['country'] for v in country_map.values()))} countries")
        return country_map
    except Exception as e:
        print(f"⚠️ Failed to fetch country map from HTML: {e}")
        return cached or {}


def get_country_map():
    """Get the component_id → country mapping. Refreshes from HTML if cache is missing or older than 24h."""
    cached = _load_country_map_from_file()
    if cached and len(cached) > 0:
        try:
            mtime = os.path.getmtime(COUNTRY_MAP_FILE)
            if time.time() - mtime < COUNTRY_MAP_TTL:
                return cached
        except OSError:
            pass
        print("🔄 Country map cache expired (24h), refreshing...")
        fresh = _fetch_country_map_from_html()
        return fresh if fresh else cached
    return _fetch_country_map_from_html()


def refresh_country_map():
    """Force-refresh the country map from the website."""
    return _fetch_country_map_from_html()


# ─── API fetchers ─────────────────────────────────────────────────────

def fetch_all_components(source):
    """Fetch the FULL list of components. Returns None on network/parse error."""
    try:
        r = requests.get(source["components_url"], timeout=15)
        r.raise_for_status()
        return r.json().get("components", [])
    except Exception as e:
        print(f"Error fetching components for {source['name']}: {e}")
        return None


def fetch_summary(source):
    """Fetch summary (for incidents). Returns None on network/parse error."""
    try:
        r = requests.get(source["summary_url"], timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Error fetching summary for {source['name']}: {e}")
        return None


def get_problem_components(source, country_map=None):
    """Return problem components from one source, or None on fetch error."""
    components = fetch_all_components(source)
    if components is None:
        return None
    if country_map is None:
        country_map = {}

    problems = []
    for comp in components:
        status = comp.get("status", "operational")
        if status in PROBLEM_STATUSES:
            comp_id = comp["id"]
            comp_name = comp["name"]

            country = ""
            flag = ""
            if source.get("has_countries") and comp_id in country_map:
                country = country_map[comp_id]["country"]
                flag = COUNTRY_FLAGS.get(country, "🌍")

            problems.append({
                "source": source["name"],
                "id": comp_id,
                "name": comp_name,
                "status": status,
                "emoji": STATUS_EMOJI.get(status, "❓"),
                "label": STATUS_LABEL.get(status, status),
                "country": country,
                "flag": flag
            })
    return problems


def get_active_incidents(source):
    """Return active incidents from one source, or None on fetch error."""
    data = fetch_summary(source)
    if data is None:
        return None

    incidents = []
    for inc in data.get("incidents", []):
        status = inc.get("status", "")
        if status not in ("resolved", "postmortem", "maintenance_complete", "completed"):
            impact = inc.get("impact", "none")
            incidents.append({
                "source": source["name"],
                "id": inc["id"],
                "name": inc["name"],
                "status": status,
                "impact": impact,
                "impact_emoji": IMPACT_EMOJI.get(impact, "⚪"),
                "created_at": inc.get("created_at", ""),
                "updated_at": inc.get("updated_at", ""),
                "page_url": source["page_url"]
            })
    return incidents


def get_all_problems():
    """
    Fetch problems and active incidents from ALL sources.
    Returns (components, incidents, had_errors).
    had_errors=True means at least one API call failed; results may be incomplete.
    """
    country_map = get_country_map()

    all_components = []
    all_incidents = []
    had_errors = False

    for source in API_SOURCES:
        comps = get_problem_components(source, country_map)
        if comps is None:
            had_errors = True
        else:
            all_components.extend(comps)

        incs = get_active_incidents(source)
        if incs is None:
            had_errors = True
        else:
            all_incidents.extend(incs)

    return all_components, all_incidents, had_errors
