import logging
from game_state import BOTS_DB
from game_state import POWER_PLANT_OPTIONS
from typing import Dict, Any, Optional, List

logging.basicConfig(level=logging.DEBUG)

MOVE_COST = 1
EXPLORE_COST = 10
DEPLOY_COST = 10
RECONFIGURE_COST = 10
ENGINEER_COST = 100
MIN_ENGINEERS = 2


def get_agent_action(agent: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns the best possible action for the given agent.
    """
    agent_type = agent.get("type")

    if agent_type == "ENGINEER_BOT":
        return engineer_action(agent)
    elif agent_type == "FACTORY":
        return factory_action(agent)

    logging.debug(f"Agent {agent['id']} ({agent_type}) has no valid action.")
    return {"type": "NONE", "params": {}}


def engineer_action(agent: Dict[str, Any]) -> Dict[str, Any]:  # noqa: C901
    """
    Engineer logic:
    - First action must be EXPLORE (only once).
    - Then, attempt to DEPLOY power plants from the factory warehouse.
    - If deployment is not possible, MOVE toward the nearest RIVER.
    - If no movement is possible and no balance for exploring, do NOTHING.
    """
    global BOTS_DB  # Ensure we're modifying the global BOTS_DB
    engineer_location: List[int] = list(agent["location"])

    # Step 1: Ensure bot has a memory of exploration
    if "has_explored" not in BOTS_DB["agents"][agent["id"]]:
        BOTS_DB["agents"][agent["id"]]["has_explored"] = False

    if not BOTS_DB["agents"][agent["id"]]["has_explored"] and BOTS_DB["balance"] >= EXPLORE_COST:
        BOTS_DB["agents"][agent["id"]]["has_explored"] = True
        logging.debug(f"🔎 Engineer {agent['id']} is exploring the map (first action).")
        return {"type": "EXPLORE", "params": {}}

    # Step 2: Find the factory and its warehouse
    factory = None
    for agent_id, data in BOTS_DB["agents"].items():
        if data["type"] == "FACTORY":
            factory = data
            break  # Only one factory exists

    if not factory:
        logging.error(f"❌ No factory found in BOTS_DB for Engineer {agent['id']}.")
        return {"type": "NONE", "params": {}}

    factory_warehouse = factory.get("warehouse", {})

    logging.debug(f"🏭 Engineer {agent['id']} checking factory warehouse: {factory_warehouse}")

    # Step 3: Deploy a power plant if available
    for plant in ["SOLAR_PANELS", "WINDMILL", "GEOTHERMAL", "DAM"]:
        if factory_warehouse.get(plant, 0) > 0:
            deploy_location = find_nearby_location(
                engineer_location, BOTS_DB["map"], valid_terrain=["PLAINS"], max_distance=2
            )
            if deploy_location:
                factory_warehouse[plant] -= 1  # Deduct from factory warehouse
                deploy_x = engineer_location[0] + deploy_location[0]
                deploy_y = engineer_location[1] + deploy_location[1]
                BOTS_DB["map"][deploy_y][deploy_x]["agent"] = {
                    "id": agent["id"],
                    "type": plant,
                }  # Mark as occupied
                BOTS_DB["occupied_locations"].add((deploy_x, deploy_y))  # Track occupied locations
                logging.debug(
                    f"Engineer {agent['id']} is deploying {plant} at {deploy_x, deploy_y}"
                )
                return {
                    "type": "DEPLOY",
                    "params": {
                        "power_type": plant,
                        "d_loc": deploy_location
                    }
                }

    # Step 4: Move toward the river if deployment is not possible
    river_location = find_closest_river(engineer_location, BOTS_DB["map"])
    if river_location:
        move_direction = find_nearby_location(
            engineer_location,
            BOTS_DB["map"],
            target_location=river_location,
            max_distance=2,
        )
        if move_direction:
            logging.debug(
                f"Engineer {agent['id']} is moving toward the RIVER at {move_direction}"
            )
            return {"type": "MOVE", "params": {"d_loc": move_direction}}

    # Step 5: If no movement is possible and no balance for explore, do nothing
    logging.debug(f"🚫 Engineer {agent['id']} is doing NOTHING (balance={BOTS_DB['balance']})")
    return {"type": "NONE", "params": {}}


def find_closest_river(location: List[int], map_data: List[List[Any]]) -> Optional[List[int]]:
    """
    Finds the nearest RIVER tile from the given location.
    """
    x, y = location
    map_size = len(map_data)
    closest_river = None
    min_distance = float("inf")

    logging.debug(f"🌊 Searching for the nearest RIVER from {location}.")

    for row in range(map_size):
        for col in range(map_size):
            cell = map_data[row][col]
            if cell and cell.get("type") == "RIVER":
                distance = abs(x - col) + abs(y - row)  # Manhattan distance
                if distance < min_distance:
                    closest_river = [col, row]
                    min_distance = distance

    if closest_river:
        logging.debug(f"✅ Closest RIVER found at {closest_river} (distance={min_distance})")
    else:
        logging.debug("❌ No RIVER found in the map data.")

    return closest_river


def factory_action(agent: Dict[str, Any]) -> Dict[str, Any]:
    """
    Factory logic:
    Builds the first engineer if none exist.
    Prioritizes power plants if <3 in warehouse,
    ensuring at least 10 energy remains after purchase.
    Builds additional engineers if power plants are sufficient
    and energy is available for deployment.
    If none of the above is possible, does nothing.
    """
    global BOTS_DB

    warehouse = BOTS_DB.get("agents", {}).get(agent["id"], {}).get("warehouse", {})
    existing_engineers = sum(1 for a in BOTS_DB["agents"].values() if a["type"] == "ENGINEER_BOT")

    ENGINEER_COST = 100
    DEPLOY_COST = 10  # Energy needed per power plant deployment
    MIN_ENERGY_RESERVE = (existing_engineers + 1) * DEPLOY_COST  # Ensure deployment is possible

    # Step 1: If no engineers exist, build one immediately
    if existing_engineers == 0 and BOTS_DB["balance"] >= ENGINEER_COST:
        build_step = find_nearby_location(
            agent["location"],
            map_data=BOTS_DB["map"],
            max_distance=5,
            valid_terrain=["PLAINS"]
        )

        if build_step:
            build_x = agent["location"][0] + build_step[0]
            build_y = agent["location"][1] + build_step[1]

            # Ensure location is valid before building
            if (build_x, build_y) not in BOTS_DB["occupied_locations"]:
                BOTS_DB["occupied_locations"].add((build_x, build_y))
                BOTS_DB["balance"] -= ENGINEER_COST  # Deduct cost

                logging.debug(
                    f"Factory {agent['id']} is building the first engineer at {build_step}"
                )
                return {"type": "BUILD_BOT", "params": {"d_loc": build_step}}

    # Step 2: Prioritize power plant assembly if <3 in warehouse and enough energy remains
    for plant, cost in POWER_PLANT_OPTIONS:
        remaining_balance_after_purchase = BOTS_DB["balance"] - cost

        if warehouse.get(plant, 0) < 3 and remaining_balance_after_purchase >= MIN_ENERGY_RESERVE:
            BOTS_DB["balance"] -= cost  # Deduct cost
            warehouse[plant] = warehouse.get(plant, 0) + 1  # Store in warehouse

            logging.debug(
                f"Factory {agent['id']} assembling {plant}"
                f"(cost={cost}, balance after purchase={remaining_balance_after_purchase})"
            )
            return {"type": "ASSEMBLE_POWER_PLANT", "params": {"power_type": plant}}

    # Step 3: Build additional engineers **only if power plants are ready & energy remains**
    if BOTS_DB["balance"] >= (ENGINEER_COST + MIN_ENERGY_RESERVE):
        build_step = find_nearby_location(
            agent["location"],
            map_data=BOTS_DB["map"],
            max_distance=5,
            valid_terrain=["PLAINS"]
        )

        if build_step:
            build_x = agent["location"][0] + build_step[0]
            build_y = agent["location"][1] + build_step[1]

            # Ensure location is valid before building
            if (build_x, build_y) not in BOTS_DB["occupied_locations"]:
                BOTS_DB["occupied_locations"].add((build_x, build_y))
                BOTS_DB["balance"] -= ENGINEER_COST  # Deduct cost

                logging.debug(f"⚙️ Factory {agent['id']} is building an engineer at {build_step}")
                return {"type": "BUILD_BOT", "params": {"d_loc": build_step}}

    # Step 4: If no valid actions, do nothing
    logging.debug(
        f"Factory {agent['id']} is doing NOTHING (balance={BOTS_DB['balance']})"
    )
    return {"type": "NONE", "params": {}}


def find_nearby_location(
    location: List[int],
    map_data: List[List[Any]],
    max_distance: int = 2,
    valid_terrain: Optional[List[str]] = None,
    target_location: Optional[List[int]] = None
) -> Optional[List[int]]:
    """
    Finds the nearest available location for an action (movement, deployment).
    Ensures location is unoccupied and on valid terrain.
    """
    x, y = location
    map_size = len(map_data)
    closest_location = None
    min_distance = float("inf")

    logging.debug(f"🔍 Searching for a nearby location from {location} within {max_distance} tiles.")

    for dx in range(-max_distance, max_distance + 1):
        for dy in range(-max_distance, max_distance + 1):
            new_x, new_y = x + dx, y + dy

            # Ensure within map bounds
            if not (0 <= new_x < map_size and 0 <= new_y < map_size):
                continue
            # Ensure Manhattan distance is within range
            distance = abs(dx) + abs(dy)
            if distance > max_distance:
                continue

            cell = map_data[new_y][new_x]

            # Ensure the cell exists and is unoccupied
            if (
                cell is not None  # Ensure cell exists
                and "type" in cell
                and (valid_terrain is None or cell["type"] in valid_terrain)
                and (new_x, new_y) not in BOTS_DB["occupied_locations"]  # Ensure it's not occupied
            ):
                logging.debug(
                    f"Target location {(new_x, new_y)}. Occupied {BOTS_DB['occupied_locations']}"
                )
                # If moving towards a specific target, prefer locations closer to it
                if target_location:
                    target_distance = (
                        abs(target_location[0] - new_x)
                        + abs(target_location[1] - new_y)
                    )
                    if target_distance < min_distance:
                        closest_location = [dx, dy]
                        min_distance = target_distance
                else:
                    if distance < min_distance:
                        closest_location = [dx, dy]
                        min_distance = distance

                logging.debug(f"✅ Found valid location at {new_x, new_y} (dx={dx}, dy={dy})")

    if closest_location is None:
        logging.debug(f"❌ No valid locations found near {location}")
    return closest_location
