import os
import logging
from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp.mcp_client import MCPClient
from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client

logger = logging.getLogger(__name__)

#gets MCP_ENDPOINT from agentcore runtime envVar if prod, else default to localhost for dev
MCP_ENDPOINT = os.getenv("MCP_ENDPOINT", "http://localhost:8000/mcp")

#get MCP_AUTH_MODE value from envVar if prod, else just a string of none
MCP_AUTH_MODE = os.getenv("MCP_AUTH_MODE", "none")

def get_streamable_http_mcp_client() -> MCPClient:
    """Returns an MCP Client compatible with Strands"""
    if MCP_AUTH_MODE == "aws_iam":
        return MCPClient(
            lambda: aws_iam_streamablehttp_client(
                endpoint=MCP_ENDPOINT,
                aws_region="us-east-1",
                aws_service="bedrock-agentcore"
            )
        )

    return MCPClient(
        lambda: streamablehttp_client(MCP_ENDPOINT)
    )
