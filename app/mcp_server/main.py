import os
from pathlib import Path
from dotenv import load_dotenv

from mcp_tools.tools import mcp, find_oldest_parks


if os.getenv("LOCAL_DEV") == "1":
    #load .env from root directory if in local dev
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    env_path = PROJECT_ROOT / ".env"

    if not env_path.is_file():
        raise RuntimeError(f"Local env file not present. make one, buddy")

    load_dotenv(env_path)


if __name__ == "__main__":
    import asyncio
    parks = asyncio.run(find_oldest_parks())
    print(parks)
    mcp.run(transport="streamable-http")
