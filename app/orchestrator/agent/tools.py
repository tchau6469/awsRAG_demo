from mcp_client.client import get_streamable_http_mcp_client
import os

#list all tools while in local dev 
if os.getenv("LOCAL_DEV") == "1":
    mcp_client = get_streamable_http_mcp_client()

    with mcp_client:
        mcp_tools = mcp_client.list_tools_sync()

        for mcp_tool in mcp_tools:
            print(mcp_tool.tool_name)


# Define a Streamable HTTP MCP Client
mcp_clients = [get_streamable_http_mcp_client()]


# Define a collection of tools used by the model
tools = []

# Add MCP client to tools if available
for mcp_client in mcp_clients:
    if mcp_client:
        tools.append(mcp_client)