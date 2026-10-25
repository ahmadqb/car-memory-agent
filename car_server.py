"""MCP server that plays 'the car'. State is stored in a JSON file so it survives between calls."""
import json
import os

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("car")

STATE_FILE = os.getenv(
    "CAR_STATE_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "car_state.json"),
)
DEFAULT_STATE = {"cabin_temp_c": 20.0, "battery_pct": 76, "now_playing": None, "location": "Munich"}
MIN_TEMP, MAX_TEMP = 16.0, 28.0


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return {**DEFAULT_STATE, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_STATE)


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


@mcp.tool()
def get_cabin_temperature() -> float:
    """Current cabin temperature setpoint in degrees Celsius."""
    return load_state()["cabin_temp_c"]


@mcp.tool()
def set_cabin_temperature(temp_c: float) -> str:
    """Set the cabin temperature in degrees Celsius (allowed range 16 to 28)."""
    if not MIN_TEMP <= temp_c <= MAX_TEMP:
        return f"Refused: {temp_c} C is outside the allowed range {MIN_TEMP}-{MAX_TEMP} C."
    state = load_state()
    state["cabin_temp_c"] = temp_c
    save_state(state)
    return f"Cabin temperature set to {temp_c} C."


@mcp.tool()
def get_battery_level() -> int:
    """Battery state of charge in percent."""
    return load_state()["battery_pct"]


@mcp.tool()
def play_media(genre: str) -> str:
    """Start playing a playlist of the given genre, e.g. 'jazz' or 'electronic'."""
    state = load_state()
    state["now_playing"] = genre
    save_state(state)
    return f"Now playing: {genre} playlist."


@mcp.tool()
def get_current_location() -> str:
    """Current location of the vehicle (mock data)."""
    return load_state()["location"]


if __name__ == "__main__":
    mcp.run(transport="stdio")