"""MCP server that plays 'the car'. Run by an MCP client over stdio (see test_client.py)."""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("car")

# Mock vehicle state (lives as long as the server process)
STATE = {"cabin_temp_c": 20.0, "battery_pct": 76, "now_playing": None, "location": "Munich"}

MIN_TEMP, MAX_TEMP = 16.0, 28.0


@mcp.tool()
def get_cabin_temperature() -> float:
    """Current cabin temperature setpoint in degrees Celsius."""
    return STATE["cabin_temp_c"]


@mcp.tool()
def set_cabin_temperature(temp_c: float) -> str:
    """Set the cabin temperature in degrees Celsius (allowed range 16 to 28)."""
    if not MIN_TEMP <= temp_c <= MAX_TEMP:
        return f"Refused: {temp_c} C is outside the allowed range {MIN_TEMP}-{MAX_TEMP} C."
    STATE["cabin_temp_c"] = temp_c
    return f"Cabin temperature set to {temp_c} C."


@mcp.tool()
def get_battery_level() -> int:
    """Battery state of charge in percent."""
    return STATE["battery_pct"]


@mcp.tool()
def play_media(genre: str) -> str:
    """Start playing a playlist of the given genre, e.g. 'jazz' or 'electronic'."""
    STATE["now_playing"] = genre
    return f"Now playing: {genre} playlist."


@mcp.tool()
def get_current_location() -> str:
    """Current location of the vehicle (mock data)."""
    return STATE["location"]


if __name__ == "__main__":
    mcp.run(transport="stdio")
