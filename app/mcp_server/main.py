import os
from pathlib import Path
from dotenv import load_dotenv

from mcp_tools.tools import mcp

#load .env from root directory if in local dev
if os.getenv("LOCAL_DEV") == "1":
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    env_path = PROJECT_ROOT / ".env"

    if not env_path.is_file():
        raise RuntimeError(f"Local env file not present. make one, buddy")
    
    print("RUNNING IN LOCAL DEV MODE")
    load_dotenv(env_path)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
