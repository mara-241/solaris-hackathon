"""
LangGraph supervisor graph for Solaris.

Nodes
-----
- **supervisor** – LLM decides which tool to call next (or finish).
- **tool_executor** – Runs the selected tool and stores the result.
- **replanner** – Checks quality (e.g. cloud cover) and may replan.

The graph is compiled once via ``build_graph()`` and invoked per-request
through ``run_solaris_graph()``.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from agents.langgraph.prompts import SUPERVISOR_SYSTEM_PROMPT
from agents.langgraph.tools import ALL_TOOLS

logger = logging.getLogger(__name__)

# ── LLM configuration ───────────────────────────────────────────────────────
# Uses Qwen 3.5 via any OpenAI-compatible endpoint (DashScope, Ollama, etc.)
# Configure via environment variables.

from dotenv import load_dotenv
load_dotenv()

_DEFAULT_MODEL = os.getenv("SOLARIS_LLM_MODEL", "qwen3.5")
_DEFAULT_BASE_URL = os.getenv(
    "SOLARIS_LLM_BASE_URL",
    "http://localhost:11434/v1",  # Ollama default
)
_DEFAULT_API_KEY = os.getenv("SOLARIS_LLM_API_KEY", "ollama")  # Ollama doesn't need a real key

CLOUD_COVER_THRESHOLD = 30.0
MAX_SATELLITE_RETRIES = 2


def _get_llm() -> ChatOpenAI:
    """Instantiate the LLM used by the supervisor."""
    return ChatOpenAI(
        model=_DEFAULT_MODEL,
        base_url=_DEFAULT_BASE_URL,
        api_key=_DEFAULT_API_KEY,
        temperature=0.3,
    )


# ── State schema (TypedDict) ────────────────────────────────────────────────

from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """State that flows through the graph."""
    messages: Annotated[list, add_messages]
    request: dict
    perception_result: dict | None
    spatial_result: dict | None
    satellite_result: dict | None
    energy_result: dict | None
    evidence_result: dict | None
    plan: list
    replan_reason: str | None
    completed_steps: list
    errors: list
    satellite_retries: int


# ── Node: supervisor ────────────────────────────────────────────────────────

def supervisor_node(state: AgentState) -> dict:
    """
    The LLM supervisor inspects the current state and decides which tool
    to call next, or whether we are done.
    """
    llm = _get_llm()
    plan = state.get("plan", [])
    
    # Selectively bind tools: only expose pipeline tools if they are in the plan
    from agents.langgraph.tools import (
        run_energy_analysis, perception_data, spatial_analysis, 
        satellite_imagery, energy_optimization, evidence_pack,
        geocode_location, search_stored_plans
    )
    
    available_tools = [run_energy_analysis, geocode_location, search_stored_plans]
    if "perception_data" in plan: available_tools.append(perception_data)
    if "spatial_analysis" in plan: available_tools.append(spatial_analysis)
    if "satellite_imagery" in plan: available_tools.append(satellite_imagery)
    if "energy_optimization" in plan: available_tools.append(energy_optimization)
    if "evidence_pack" in plan: available_tools.append(evidence_pack)
        
    llm_with_tools = llm.bind_tools(available_tools)

    messages = state.get("messages", [])
    logger.info("--- SUPERVISOR STARTING ---")

    # Inject system prompt if not present
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT)] + messages

    # Build a context message so the LLM knows current state
    context = _build_context_message(state)
    logger.info("Supervisor context built. Invoking LLM...")
    full_messages = messages + [HumanMessage(content=context)]

    response = llm_with_tools.invoke(full_messages)

    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            logger.info("Supervisor decided to call tool: %s", tc['name'])
    else:
        logger.info("Supervisor reached final conclusion.")

    return {"messages": [response]}


def _build_context_message(state: AgentState) -> str:
    """Build a summary of current state for the LLM."""
    parts = [
        f"**System Note**: The 'Request Parameters' block below may contain default or previous query values. DO NOT trigger an energy analysis unless the user explicitly asks for it in their current message.",
        f"**Request Parameters**: {json.dumps(state.get('request', {}), default=str)}",
        f"**Plan**: {state.get('plan', [])}",
        f"**Completed steps**: {state.get('completed_steps', [])}",
        f"**Errors**: {state.get('errors', [])}",
    ]

    if state.get("replan_reason"):
        parts.append(f"**Last replan reason**: {state['replan_reason']}")

    for key in ["perception_result", "spatial_result", "satellite_result",
                 "energy_result", "evidence_result"]:
        val = state.get(key)
        if val:
            # Just tell the LLM that the result exists, don't dump the massive JSON
            # unless it's the satellite result (needs it for cloud cover replanning checks)
            if key == "satellite_result":
                summary = json.dumps(val, default=str)
                parts.append(f"**{key}**: {summary}")
            elif isinstance(val, dict) and val.get("status") == "failed":
                parts.append(f"**{key}**: FAILED - {val.get('error')}")
            else:
                parts.append(f"**{key}**: SUCCESS (data stored in state)")

    # Determine next step
    plan = state.get("plan", [])
    completed = state.get("completed_steps", [])
    remaining = [s for s in plan if s not in completed]

    if remaining:
        parts.append(
            f"\n**Next step**: Call the `{remaining[0]}` tool. "
            f"Pass this JSON as input: {_build_tool_input(remaining[0], state)}"
        )
    elif plan:
        parts.append(
            "\n**All steps complete**. Synthesise the final energy-needs "
            "report from the accumulated results."
        )
    else:
        parts.append(
            "\n**Instructions**: Determine what the user wants. "
            "If they are just chatting or answering a question, respond conversationally and do NOT call any tools. "
            "If they expressly ask to run an energy analysis, forecast demand, or size a system, call `run_energy_analysis`. "
            "If they ask for existing plans, call `search_stored_plans`. "
            "NEVER call `perception_data`, `spatial_analysis`, `satellite_imagery`, `energy_optimization`, or `evidence_pack` individually without calling `run_energy_analysis` first."
        )

    return "\n".join(parts)


def _build_tool_input(tool_name: str, state: AgentState) -> str:
    """Build the JSON input string for a specific tool."""
    request = state.get("request", {})

    if tool_name == "perception_data":
        return json.dumps(request, default=str)
    elif tool_name == "spatial_analysis":
        return json.dumps(request, default=str)
    elif tool_name == "satellite_imagery":
        retries = state.get("satellite_retries", 0)
        return json.dumps({
            "lat": request.get("lat"),
            "lon": request.get("lon"),
            "date_offset": retries * 90,
        }, default=str)
    elif tool_name in ["energy_optimization", "evidence_pack", "run_energy_analysis"]:
        # The LLM now just passes down the original request arguments
        return json.dumps(request, default=str)
    else:
        return json.dumps(request, default=str)


# ── Node: process_tool_result ────────────────────────────────────────────────

def process_tool_result(state: AgentState) -> dict:
    """
    After the tool node runs, parse the latest tool response and store the
    result in the appropriate state field.
    """
    messages = state.get("messages", [])
    completed = list(state.get("completed_steps", []))
    errors = list(state.get("errors", []))

    # Find the latest tool message
    tool_result = None
    tool_name = None
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "tool":
            tool_name = getattr(msg, "name", None)
            try:
                tool_result = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                tool_result = {"raw": str(msg.content)}
            break

    if not tool_name:
        logger.warning("No tool name found in process_tool_result!")
        return {}

    logger.info("--- PROCESSING RESULT FOR TOOL: %s ---", tool_name)
    updates: dict[str, Any] = {}

    if tool_name not in completed:
        completed.append(tool_name)
    updates["completed_steps"] = completed

    # Check for triggers that require manual function execution
    # (Because passing massive state via the LLM context window crashes it)
    if isinstance(tool_result, dict) and "__trigger__" in tool_result:
        trigger = tool_result["__trigger__"]
        req = tool_result.get("request", {})
        
        try:
            if trigger == "run_energy_analysis":
                raw_plan = state.get("plan", [])
                plan = [str(x) for x in raw_plan] if isinstance(raw_plan, list) else []
                pipeline = [
                    "perception_data",
                    "spatial_analysis",
                    "satellite_imagery",
                    "energy_optimization",
                    "evidence_pack"
                ]
                for step in pipeline:
                    if step not in plan:
                        plan.append(step)
                updates["plan"] = plan
                tool_result = {"status": "ok", "message": "Pipeline triggered successfully. Proceed with the newly configured plan steps."}
            elif trigger == "energy_optimization":
                from agents.energy_optimization.agent import optimize_energy_plan
                tool_result = optimize_energy_plan(
                    feature_context={
                        "perception": state.get("perception_result", {}),
                        "spatial": state.get("spatial_result", {})
                    }
                )
            elif trigger == "evidence_pack":
                from agents.evidence.agent import build_evidence_pack
                energy = state.get("energy_result", {})
                
                # Check for degraded status to pass down
                all_results = [state.get("perception_result", {}), state.get("spatial_result", {}), energy]
                is_degraded = any(r.get("status") == "degraded" for r in all_results if isinstance(r, dict))
                quality = {"status": "degraded" if is_degraded else "ok"}

                tool_result = build_evidence_pack(
                    request=req,
                    feature_context={"spatial": state.get("spatial_result", {})},
                    optimization=energy
                )
        except Exception as exc:
            logger.exception(f"Trigger {trigger} failed")
            tool_result = {"status": "failed", "error": str(exc)}

    # Check for errors
    if isinstance(tool_result, dict) and tool_result.get("status") == "failed":
        errors.append(f"{tool_name}: {tool_result.get('error', 'unknown')}")
        updates["errors"] = errors

    # Store in the right state field
    field_map = {
        "perception_data": "perception_result",
        "spatial_analysis": "spatial_result",
        "satellite_imagery": "satellite_result",
        "energy_optimization": "energy_result",
        "evidence_pack": "evidence_result",
    }

    if tool_name in field_map:
        updates[field_map[tool_name]] = tool_result

    # Handle satellite replanning
    if tool_name == "satellite_imagery":
        retries = state.get("satellite_retries", 0)
        is_cloudy = isinstance(tool_result, dict) and tool_result.get("is_cloudy", False)
        avg_cc = tool_result.get("avg_cloud_cover") if isinstance(tool_result, dict) else None

        if is_cloudy and retries < MAX_SATELLITE_RETRIES:
            # Replan: insert another satellite_imagery at the front
            plan = list(state.get("plan", []))
            remaining = [s for s in plan if s not in completed or s == "satellite_imagery"]

            # Remove satellite_imagery from completed so it can run again
            if "satellite_imagery" in completed:
                completed.remove("satellite_imagery")
            updates["completed_steps"] = completed
            updates["satellite_retries"] = retries + 1
            updates["replan_reason"] = (
                f"Cloud cover {avg_cc}% > threshold {CLOUD_COVER_THRESHOLD}% — "
                f"retrying with date_offset={( retries + 1) * 90} days "
                f"(retry {retries + 1}/{MAX_SATELLITE_RETRIES})"
            )
            logger.info("Replanning satellite: %s", updates["replan_reason"])

    return updates


# ── Routing logic ────────────────────────────────────────────────────────────

def should_continue(state: AgentState) -> Literal["tools", "process", "end"]:
    """Decide where to route after the supervisor node."""
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None

    if last_message and hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    # Check if plan is complete
    plan = state.get("plan", [])
    completed = state.get("completed_steps", [])
    remaining = [s for s in plan if s not in completed]

    if not remaining:
        return "end"

    # If LLM didn't make a tool call but plan is not done, try again
    return "end"


def after_tools(state: AgentState) -> Literal["process"]:
    """Always process tool results after tool execution."""
    return "process"


def after_process(state: AgentState) -> Literal["supervisor"]:
    """After processing, go back to supervisor to decide next steps or synthesize."""
    return "supervisor"


# ── Graph builder ────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """
    Build and compile the Solaris LangGraph supervisor graph.

    .. code-block:: text

        ┌──────────┐     tool_calls     ┌───────┐
        │supervisor│ ──────────────────► │ tools │
        └──────────┘                    └───────┘
             ▲                              │
             │                              ▼
             │          ┌─────────┐
             └───────── │ process │
                        └─────────┘
                            │
                            ▼
                          [END]
    """
    tool_node = ToolNode(ALL_TOOLS)

    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("tools", tool_node)
    graph.add_node("process", process_tool_result)

    # Set entry point
    graph.set_entry_point("supervisor")

    # Edges
    graph.add_conditional_edges(
        "supervisor",
        should_continue,
        {
            "tools": "tools",
            "process": "process",
            "end": END,
        },
    )
    graph.add_edge("tools", "process")
    graph.add_conditional_edges(
        "process",
        after_process,
        {
            "supervisor": "supervisor",
            "end": END,
        },
    )

    return graph.compile()


# ── Public API ───────────────────────────────────────────────────────────────

_compiled_graph = None


def get_graph():
    """Get or build the compiled graph (singleton)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def run_solaris_graph(
    message: str,
    lat: float,
    lon: float,
    households: int | None = None,
    horizon_days: int = 30,
    thread_id: str | None = None,
    usage_profile: str | None = None,
) -> dict:
    """
    Execute the Solaris LangGraph agent.

    Parameters
    ----------
    message : str
        The user's natural-language request.
    lat, lon : float
        Location coordinates.
    households : int | None
        Number of households.
    horizon_days : int
        Forecast horizon in days.
    thread_id : str | None
        Conversation thread ID for follow-up questions.
    usage_profile : str | None
        Usage profile label.

    Returns
    -------
    dict
        Final state including all tool results and the agent's response.
    """
    graph = get_graph()

    request = {
        "request_id": thread_id or str(uuid.uuid4()),
        "lat": lat,
        "lon": lon,
        "households": households or 100,
        "horizon_days": horizon_days,
        "usage_profile": usage_profile,
    }

    initial_state: AgentState = {
        "messages": [HumanMessage(content=message)],
        "request": request,
        "perception_result": None,
        "spatial_result": None,
        "satellite_result": None,
        "energy_result": None,
        "evidence_result": None,
        "plan": [],
        "replan_reason": None,
        "completed_steps": [],
        "errors": [],
        "satellite_retries": 0,
    }

    config = {"configurable": {"thread_id": thread_id or request["request_id"]}}

    logger.info("--- STARTING LANGGRAPH EXECUTION [Thread: %s] ---", config["configurable"]["thread_id"])
    logger.info("Initial Message: %s", message)

    try:
        final_state = graph.invoke(initial_state, config=config)
        logger.info("--- LANGGRAPH EXECUTION COMPLETE ---")
    except Exception as exc:
        logger.exception("LangGraph execution failed")
        final_state = {
            **initial_state,
            "errors": [str(exc)],
        }

    # Extract the final AI response
    last_ai_message = None
    for msg in reversed(final_state.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.content:
            last_ai_message = msg.content
            break

    return {
        "thread_id": config["configurable"]["thread_id"],
        "response": last_ai_message or "Analysis complete.",
        "request": request,
        "perception_result": final_state.get("perception_result"),
        "spatial_result": final_state.get("spatial_result"),
        "satellite_result": final_state.get("satellite_result"),
        "energy_result": final_state.get("energy_result"),
        "evidence_result": final_state.get("evidence_result"),
        "completed_steps": final_state.get("completed_steps", []),
        "errors": final_state.get("errors", []),
        "replan_reason": final_state.get("replan_reason"),
    }
