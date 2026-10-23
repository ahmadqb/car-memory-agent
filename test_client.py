"""python test_client.py -> starts car_server.py, lists its tools and calls a few of them."""
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command=sys.executable, args=["car_server.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools exposed by the car:")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description}")

            for name, args in [
                ("get_cabin_temperature", {}),
                ("set_cabin_temperature", {"temp_c": 22}),
                ("get_cabin_temperature", {}),
                ("set_cabin_temperature", {"temp_c": 40}),   # must be refused
                ("play_media", {"genre": "electronic"}),
                ("get_battery_level", {}),
            ]:
                result = await session.call_tool(name, args)
                print(f"{name}({args}) -> {result.content[0].text}")


if __name__ == "__main__":
    asyncio.run(main())
