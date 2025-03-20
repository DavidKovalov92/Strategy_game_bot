import logging
from flask import Flask, Response, request, jsonify
from typing import Dict, Any, Optional
from game_state import BOTS_DB
from agents_logic import get_agent_action

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

app = Flask(__name__)


@app.get('/health')
def health() -> Response:
    """Check server health."""
    logging.info(f"Request to /health | Method: {request.method}")
    response = Response(status=200)
    logging.info(f"Response from /health: {response.status}")
    return response


@app.post('/init')
def init() -> "Response | tuple[Response, int]":
    """Initialize game state at the beginning."""
    data: Optional[Dict[str, Any]] = request.json

    if not isinstance(data, dict):
        logging.error("❌ Invalid request data. Expected a JSON object.")
        return jsonify({"error": "Invalid request data"}), 400
    BOTS_DB["map_size"] = data.get("map_size", 25)
    BOTS_DB["init_balance"] = data.get("init_balance", 300)
    BOTS_DB["team"] = data.get("team", "blue")
    BOTS_DB["balance"] = BOTS_DB["init_balance"]

    if "map" in data:
        BOTS_DB["map"] = data["map"]
        logging.info(
            f"Map size: {BOTS_DB['map_size']}x{BOTS_DB['map_size']}"
        )
    else:
        BOTS_DB["map"] = [
            [{"type": "PLAINS"} for _ in range(BOTS_DB["map_size"])]
            for _ in range(BOTS_DB["map_size"])
        ]
        logging.warning(
            f"No map data received from the platform, generating default "
            f"{BOTS_DB['map_size']}x{BOTS_DB['map_size']} PLAINS map."
        )
    response = Response(status=200)
    logging.info(f"Response from /init: {response.status}")

    return response


@app.post('/agent/<int:agent_id>')
def create_or_update_agent(agent_id: int) -> "Response | tuple[Response, int]":
    """Create a new agent or update an existing one."""
    data = request.json

    if not isinstance(data, dict):
        logging.error("❌ Invalid request data. Expected a JSON object.")
        return jsonify({"error": "Invalid request data"}), 400
    logging.info(f"Request to /agent/{agent_id} | Method: {request.method} | Body: {data}")

    # Extract agent details
    agent_location = tuple(data.get("location", (0, 0)))
    agent_type = data.get("type", "UNKNOWN")

    # Ensure the agent's warehouse exists (only for factories)
    warehouse = data.get("warehouse", {}) if agent_type == "FACTORY" else None

    # Store agent in the database
    BOTS_DB["agents"][agent_id] = {
        "id": data.get("id"),
        "type": agent_type,
        "location": agent_location,
        "team": data.get("team"),
        "warehouse": warehouse,
    }

    # Add agent location to occupied locations
    BOTS_DB["occupied_locations"].add(agent_location)

    # Update the map to reflect the agent's presence
    x, y = agent_location
    if BOTS_DB["map"] and 0 <= y < len(BOTS_DB["map"]) and 0 <= x < len(BOTS_DB["map"][y]):
        if BOTS_DB["map"][y][x] is None:
            BOTS_DB["map"][y][x] = {}  # Initialize cell if empty
        BOTS_DB["map"][y][x]["agent"] = {
            "id": agent_id,
            "type": agent_type,
            "team": data.get("team"),
            "location": list(agent_location),
        }
        logging.debug(f"Map updated: Agent {agent_id} placed at {agent_location}")

    response = Response(status=200)
    logging.info(f"Response from /agent/{agent_id}: {response.status}")
    return response


@app.post('/round')
def new_round() -> "Response | tuple[Response, int]":
    """Process new round information."""
    data = request.json

    if not isinstance(data, dict):
        logging.error("Invalid request data. Expected a JSON object.")
        return jsonify({"error": "Invalid request data"}), 400

    logging.info(f"Request to /round | Method: {request.method} | Body: {data}")

    BOTS_DB["round"] = data.get("round")
    BOTS_DB["balance"] = data.get("balance")

    response = Response(status=200)
    logging.info(f"Response from /round: {response.status}")
    return response


@app.get('/agent/<int:agent_id>/action')
def agent_action(agent_id: int) -> "Response | tuple[Response, int]":
    """Determine the action for a given agent."""
    logging.info(f"Request to /agent/{agent_id}/action | Method: {request.method}")

    agent = BOTS_DB["agents"].get(agent_id)
    if not agent:
        logging.warning(f"Agent {agent_id} not found")
        return jsonify({"error": "Agent not found"}), 404
    action = get_agent_action(agent)

    logging.info(f"Response from /agent/{agent_id}/action: {action}")
    return jsonify(action), 200


@app.patch('/agent/<int:agent_id>')
def patch_agent(agent_id: int) -> "Response | tuple[Response, int]":
    """Update an agent's state (location, warehouse)."""
    data = request.json

    if not isinstance(data, dict):
        logging.error("Invalid request data. Expected a JSON object.")
        return jsonify({"error": "Invalid request data"}), 400

    agent = BOTS_DB["agents"].get(agent_id)
    if not agent:
        return jsonify({"error": "Agent not found"}), 404

    # Track location change (free the old one, reserve the new one)
    old_location = tuple(agent["location"]) if "location" in agent else None
    new_location = tuple(data["location"]) if "location" in data else None

    if old_location and old_location in BOTS_DB["occupied_locations"]:
        BOTS_DB["occupied_locations"].remove(old_location)

    if new_location:
        BOTS_DB["occupied_locations"].add(new_location)
        agent["location"] = data["location"]

    # Update warehouse if provided
    if "warehouse" in data and isinstance(data["warehouse"], dict):
        agent["warehouse"] = data["warehouse"]

    logging.info(f"Request to /agent/{agent_id} | Method: {request.method} | Body: {data}")
    response = Response(status=200)
    logging.info(f"Response from /agent/{agent_id}: {response.status}")

    return response


@app.delete('/agent/<int:agent_id>')
def delete_agent(agent_id: int) -> "Response | tuple[Response, int]":
    """Delete an agent from the game state."""
    logging.info(f"Request to /agent/{agent_id} | Method: {request.method}")

    if agent_id not in BOTS_DB["agents"]:
        logging.warning(f"Attempted to delete non-existent agent {agent_id}")
        return jsonify({"error": "Agent not found"}), 404

    del BOTS_DB["agents"][agent_id]

    response = Response(status=200)
    logging.info(f"Response from /agent/{agent_id}: {response.status}")
    return response


@app.post('/agent/<int:agent_id>/view')
def agent_view(agent_id: int) -> "Response | tuple[Response, int]":  # noqa: C901
    """Processes the agent's view of the map, updating BOTS_DB and tracking occupied locations."""
    data = request.json

    if not isinstance(data, dict):
        logging.error("Invalid request data. Expected a JSON object.")
        return jsonify({"error": "Invalid request data"}), 400

    logging.info(f"Request to /agent/{agent_id}/view | Method: {request.method}")

    # Validate incoming map data
    if "map" not in data or not isinstance(data["map"], list):
        logging.error("Invalid or missing 'map' key in request body.")
        return jsonify({"error": "Missing or invalid 'map' key in request body"}), 400

    # Get the expected map size
    map_size = BOTS_DB.get("map_size", 24)  # Default size if missing

    # Ensure `BOTS_DB["map"]` is initialized with the correct size
    if not isinstance(BOTS_DB.get("map"), list) or len(BOTS_DB["map"]) != map_size:
        BOTS_DB["map"] = [[None for _ in range(map_size)] for _ in range(map_size)]
        logging.info(f"🔄 Initialized empty {map_size}x{map_size} map in BOTS_DB.")

    # Ensure `occupied_locations` is always a set
    if "occupied_locations" not in BOTS_DB or not isinstance(BOTS_DB["occupied_locations"], set):
        BOTS_DB["occupied_locations"] = set()

    # Do not clear `occupied_locations` entirely—track only updated cells
    updated_locations = set()

    for y, row in enumerate(data["map"]):
        if not isinstance(row, list):
            logging.error(f"❌ Invalid row format in map data at index {y}: {row}")
            continue  # Skip invalid rows

        for x, cell in enumerate(row):
            if y >= map_size or x >= map_size:
                logging.warning(f"❌ Skipping out-of-bounds update at ({x}, {y})")
                continue

            # Skip updating if cell is None (preserve existing data)
            if cell is None:
                continue

            if "location" in cell and isinstance(cell["location"], list):
                location = cell["location"]
                if not isinstance(location, list) or len(location) != 2:
                    logging.warning(f"❌ Skipping invalid location format: {location}")
                    continue

                # Convert None values inside the cell to `None`
                cleaned_cell = {k: v if v is not None else None for k, v in cell.items()}

                # ✅ Update only if there is a change (avoid unnecessary overwrites)
                if BOTS_DB["map"][y][x] is None or BOTS_DB["map"][y][x] != cleaned_cell:
                    BOTS_DB["map"][y][x] = cleaned_cell  # Store updated cell

                    # Track occupied locations where 'agent' is present
                    if "agent" in cleaned_cell and cleaned_cell["agent"] is not None:
                        updated_locations.add(tuple(location))
                        logging.debug(f"🚧 Marked ({x}, {y}) as occupied by {cleaned_cell['agent']}")

    # ✅ Remove only locations that changed from `occupied_locations`
    BOTS_DB["occupied_locations"].update(updated_locations)

    logging.info(f"✅ Successfully updated map from agent {agent_id}")
    logging.info(f"📍 Occupied locations: {BOTS_DB['occupied_locations']}")

    return jsonify({"message": "Map updated successfully"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
