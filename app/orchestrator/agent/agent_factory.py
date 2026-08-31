from model.load import load_model
from strands.agent.conversation_manager.null_conversation_manager import NullConversationManager
from memory.session import get_memory_session_manager
from strands import Agent
from pydantic import BaseModel

def _make_conversation_manager():
    return NullConversationManager()


def agent_factory(
    tools: list | None = None,
    prompt: str = "",
    structured_output_model: type[BaseModel] | None = None,
    use_session_manager: bool = True,
):
    cache = {}
    def get_or_create_agent(session_id, user_id):
        _actor_id = user_id
        key = f"{session_id}/{_actor_id}"
        if key not in cache:
            cache[key] = Agent(
                model=load_model(),
                session_manager=(
                    get_memory_session_manager(session_id, _actor_id)
                    if use_session_manager
                    else None
                ),
                conversation_manager=_make_conversation_manager(),
                system_prompt=prompt,
                tools=tools,
                structured_output_model=structured_output_model,
                hooks=[
                ],
            )
        return cache[key]
    return get_or_create_agent
