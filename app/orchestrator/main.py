import os
from typing import Any
from collections import OrderedDict
import asyncio
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from agent.tools import tools
from agent.graph import create_content_loop
from prompts import DEFAULT_SYSTEM_PROMPT
from agent.agent_factory import agent_factory

app = BedrockAgentCoreApp()
log = app.logger



_INLINE_FUNCTION_NAMES = set()

WORKFLOW_MODE = os.getenv("WORKFLOW_MODE", "agent")



def strip_trailing_tool_use(messages: Any) -> list[dict]:
    """Strip toolUse blocks from the tail until the last message has none."""
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")

    messages = list(messages)
    while messages:
        last = messages[-1]
        if not isinstance(last, dict):
            raise ValueError("each message must be an object")
        original_content = last.get("content", [])
        if not isinstance(original_content, list) or not all(isinstance(block, dict) for block in original_content):
            raise ValueError("each message content value must be a list of content blocks")

        content = [block for block in original_content if "toolUse" not in block]
        if len(content) == len(original_content):
            break
        if content:
            messages[-1] = {**last, "content": content}
            break
        messages.pop()

    return messages


def _extract_prompt(payload: dict):
    """Accept validated harness messages, tool results, or a plain prompt string."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    if "messages" in payload:
        return strip_trailing_tool_use(payload["messages"])
    if "tool_results" in payload:
        tool_results = payload["tool_results"]
        if not isinstance(tool_results, list) or not all(
            isinstance(tool_result, dict) and isinstance(tool_result.get("toolUseId"), str)
            for tool_result in tool_results
        ):
            raise ValueError("tool_results must contain objects with a toolUseId string")
        return [{"role": "user", "content": [{"toolResult": {
            "toolUseId": tr["toolUseId"],
            "status": tr.get("status", "success"),
            "content": tr.get("content", []),
        }} for tr in tool_results]}]
    prompt = payload.get("prompt", "")
    if not isinstance(prompt, str):
        raise ValueError("prompt must be a string")
    return prompt


def _has_inline_function_call(messages) -> bool:
    """Return True if messages contains an assistant toolUse for an inline function tool."""
    if not _INLINE_FUNCTION_NAMES or not isinstance(messages, list):
        return False
    for msg in messages:
        if msg.get("role") == "assistant":
            for block in msg.get("content", []):
                if isinstance(block, dict) and block.get("toolUse", {}).get("name") in _INLINE_FUNCTION_NAMES:
                    return True
    return False


def _is_inline_function_call(event: dict) -> bool:
    """Check if a contentBlockStart event is for an inline function tool."""
    if not _INLINE_FUNCTION_NAMES:
        return False
    cbs = event.get("contentBlockStart", {})
    start = cbs.get("start", {})
    tool_use = start.get("toolUse") if isinstance(start, dict) else None
    return tool_use is not None and tool_use.get("name") in _INLINE_FUNCTION_NAMES


get_default_agent = agent_factory(tools, DEFAULT_SYSTEM_PROMPT)

@app.entrypoint
async def invoke(payload, context):

    log.info("Invoking Agent.....")

    prompt = _extract_prompt(payload)
    session_id = getattr(context, 'session_id', 'default-session')
    user_id = getattr(context, 'user_id', 'default-user')

    if WORKFLOW_MODE == "graph":
        graph = create_content_loop(session_id, user_id)
        async for graph_event in graph.stream_async(prompt):
            if graph_event.get("type") != "multiagent_node_stream":
                continue
            if graph_event.get("node_id") != "synthesis":
                continue

            agent_event = graph_event.get("event")
            if not isinstance(agent_event, dict) or "event" not in agent_event:
                continue

            cbs = agent_event["event"].get("contentBlockStart")
            if cbs is not None and not cbs.get("start"):
                continue

            yield agent_event
        return

    agent = get_default_agent(session_id, user_id)
    async for event in agent.stream_async(prompt):
        if not isinstance(event, dict) or "event" not in event:
            continue

        cbs = event["event"].get("contentBlockStart")
        if cbs is not None and not cbs.get("start"):
            continue

        yield event


if __name__ == "__main__":
    app.run()
