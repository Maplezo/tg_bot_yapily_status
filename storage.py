import json
import os
import threading
from typing import Dict, Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, 'db.json')

_lock = threading.Lock()


def _load() -> Dict[str, Any]:
    if not os.path.exists(DB_FILE):
        return {"notified_incidents": {}}
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {"notified_incidents": {}}


def _save(data: Dict[str, Any]):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)


def get_notified_incidents() -> Dict[str, Dict[str, str]]:
    """Returns dict of {incident_id: {"status": ..., "name": ...}}."""
    with _lock:
        raw = _load().get("notified_incidents", {})
    # Migrate old format {id: status_string} → {id: {"status": ..., "name": ...}}
    return {
        k: v if isinstance(v, dict) else {"status": v, "name": k}
        for k, v in raw.items()
    }


def update_notified_incidents(incidents: Dict[str, Dict[str, str]]):
    """Overwrite the stored incidents with their latest status and name."""
    with _lock:
        data = _load()
        data["notified_incidents"] = incidents
        _save(data)
