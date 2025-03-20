from typing import Dict, Any

BOTS_DB: Dict[str, Any] = {
    "map_size": None,
    "init_balance": None,
    "team": None,
    "round": 0,
    "balance": 0,
    "agents": {},
    "occupied_locations": set(),
    "map": []
}

POWER_PLANT_OPTIONS = [
    ("WINDMILL", 100),
    ("SOLAR_PANELS", 500),
    ("GEOTHERMAL", 500),
    ("DAM", 1000)
]
