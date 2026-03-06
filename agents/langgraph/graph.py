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
import time
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
# Single satellite execution per run (no retry pass).
MAX_SATELLITE_RETRIES = 0
MAX_SUPERVISOR_CONTEXT_CHARS = 12000
MAX_SUPERVISOR_TOTAL_CHARS = 20000
MAX_SUPERVISOR_TOKEN_LIMIT = 200000
TARGET_SUPERVISOR_TOKENS = 180000
EST_CHARS_PER_TOKEN = 4.0


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
    graph_started_at_ms: float
    last_tool_ts_ms: float | None
    step_durations_ms: dict


def _truncate_text(value: str, limit: int = 1200) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...[truncated]"


def _estimate_tokens_for_messages(messages: list) -> int:
    total_chars = sum(len(str(getattr(m, "content", ""))) for m in messages)
    # Rough estimation for OpenAI-compatible tokenization.
    return int(total_chars / EST_CHARS_PER_TOKEN) + (len(messages) * 8)


def _compact_history(messages: list) -> list:
    """
    Keep only compact conversational messages for supervisor calls.
    Tool payloads are summarized via state fields separately.
    """
    compact: list = []
    for msg in messages:
        mtype = getattr(msg, "type", "")
        if mtype == "tool":
            continue
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            continue
        if isinstance(msg, SystemMessage):
            continue
        text = _truncate_text(str(getattr(msg, "content", "")), limit=1200)
        if isinstance(msg, HumanMessage):
            compact.append(HumanMessage(content=text))
        elif isinstance(msg, AIMessage):
            compact.append(AIMessage(content=text))
    return compact[-4:]


def _safe_result_slice(value: dict, keys: list[str]) -> dict:
    out = {}
    for key in keys:
        if key in value:
            out[key] = value.get(key)
    return out


def _summarize_state_result(key: str, value: dict) -> str:
    if not isinstance(value, dict):
        return "unavailable"
    if value.get("status") == "failed":
        return f"FAILED: {value.get('error', 'unknown')}"

    if key == "perception_result":
        weather = value.get("weather", {}) if isinstance(value.get("weather"), dict) else {}
        demographics = value.get("demographics", {}) if isinstance(value.get("demographics"), dict) else {}
        summary = {
            "status": value.get("status"),
            "confidence": value.get("confidence"),
            "weather": _safe_result_slice(weather, ["sun_hours", "rain_risk", "source"]),
            "demographics": _safe_result_slice(demographics, ["households", "country_code", "source"]),
            "quality_flags": value.get("quality_flags", [])[:6],
        }
        return json.dumps(summary, default=str)

    if key == "spatial_result":
        fs = value.get("feature_summaries", {}) if isinstance(value.get("feature_summaries"), dict) else {}
        summary = {
            "status": value.get("status"),
            "confidence": value.get("confidence"),
            "feature_summaries": _safe_result_slice(
                fs,
                [
                    "ndvi_mean",
                    "ndwi_mean",
                    "water_coverage_pct",
                    "settlement_density",
                    "scene_date",
                    "sentinel_scene_count",
                    "error",
                ],
            ),
            "quality_flags": value.get("quality_flags", [])[:6],
        }
        return json.dumps(summary, default=str)

    if key == "satellite_result":
        summary = _safe_result_slice(
            value,
            [
                "status",
                "source",
                "sentinel_scene_count",
                "avg_cloud_cover",
                "best_scene_cloud_cover",
                "ndvi_estimate",
                "is_cloudy",
                "date_range",
            ],
        )
        return json.dumps(summary, default=str)

    if key == "energy_result":
        demand = value.get("demand_forecast", {}) if isinstance(value.get("demand_forecast"), dict) else {}
        primary = (
            value.get("scenario_set", {}).get("primary", {})
            if isinstance(value.get("scenario_set"), dict)
            else {}
        )
        summary = {
            "status": value.get("status"),
            "confidence": value.get("confidence"),
            "demand_forecast": _safe_result_slice(demand, ["kwh_per_day", "lower_ci", "upper_ci"]),
            "primary_plan": _safe_result_slice(primary, ["pv_kw", "battery_kwh", "solar_kits"]),
            "quality_flags": value.get("quality_flags", [])[:6],
        }
        return json.dumps(summary, default=str)

    if key == "evidence_result":
        summary = _safe_result_slice(value, ["status", "confidence", "summary", "quality_flags"])
        return json.dumps(summary, default=str)

    return "SUCCESS"

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

    # Keep supervisor input compact to avoid context overflows.
    compact_history = _compact_history(messages)

    # Build a context message so the LLM knows current state.
    context = _build_context_message(state)
    logger.info("Supervisor context built. Invoking LLM...")
    full_messages = [SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT)] + compact_history + [HumanMessage(content=context)]

    total_chars = sum(len(str(getattr(m, "content", ""))) for m in full_messages)
    estimated_tokens = _estimate_tokens_for_messages(full_messages)
    if total_chars > MAX_SUPERVISOR_TOTAL_CHARS or estimated_tokens > TARGET_SUPERVISOR_TOKENS:
        # Token-budget guardrail: progressively drop history, then truncate context.
        while compact_history and estimated_tokens > TARGET_SUPERVISOR_TOKENS:
            compact_history = compact_history[1:]
            full_messages = [SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT)] + compact_history + [HumanMessage(content=context)]
            estimated_tokens = _estimate_tokens_for_messages(full_messages)

        if estimated_tokens > TARGET_SUPERVISOR_TOKENS:
            context = _truncate_text(context, MAX_SUPERVISOR_TOTAL_CHARS // 2)
            full_messages = [SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT)] + compact_history + [HumanMessage(content=context)]
            estimated_tokens = _estimate_tokens_for_messages(full_messages)

        logger.warning(
            "Supervisor payload trimmed. chars=%s estimated_tokens=%s",
            sum(len(str(getattr(m, "content", ""))) for m in full_messages),
            estimated_tokens,
        )
    else:
        logger.info("Supervisor payload size chars=%s estimated_tokens=%s", total_chars, estimated_tokens)

    if estimated_tokens > MAX_SUPERVISOR_TOKEN_LIMIT:
        # Hard stop before API call.
        raise RuntimeError(
            f"supervisor payload too large after trimming: estimated_tokens={estimated_tokens}"
        )

    response = llm_with_tools.invoke(full_messages)

    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            logger.info("Supervisor decided to call tool: %s", tc['name'])
    else:
        logger.info("Supervisor reached final conclusion.")

    return {"messages": [response]}


def _build_context_message(state: AgentState) -> str:
    """Build a compact summary of current state for the LLM."""
    parts = [
        "**System Note**: Use only current user intent; avoid re-running analysis unless requested.",
        f"**Request Parameters**: {json.dumps(state.get('request', {}), default=str)}",
        f"**Plan**: {state.get('plan', [])}",
        f"**Completed steps**: {state.get('completed_steps', [])}",
        f"**Errors**: {state.get('errors', [])}",
    ]

    if state.get("replan_reason"):
        parts.append(f"**Last replan reason**: {state['replan_reason']}")

    for key in ["perception_result", "spatial_result", "satellite_result", "energy_result", "evidence_result"]:
        value = state.get(key)
        if value:
            parts.append(f"**{key} summary**: {_summarize_state_result(key, value)}")

    plan = state.get("plan", [])
    completed = state.get("completed_steps", [])
    remaining = [s for s in plan if s not in completed]

    if remaining:
        next_tool = remaining[0]
        parts.append(
            f"**Next step**: Call `{next_tool}` with: {_build_tool_input(next_tool, state)}"
        )
    elif plan:
        parts.append("**All steps complete**: produce a concise completion response.")
    else:
        parts.append(
            "**Instructions**: detect intent. Greetings => conversational reply only. "
            "Analysis request => call `run_energy_analysis`. Existing plans => call `search_stored_plans`."
        )

    context = "\n".join(parts)
    if len(context) > MAX_SUPERVISOR_CONTEXT_CHARS:
        context = _truncate_text(context, MAX_SUPERVISOR_CONTEXT_CHARS)
    return context


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
    elif tool_name == "energy_optimization":
        return json.dumps(request, default=str)
    elif tool_name == "evidence_pack":
        return json.dumps(request, default=str)
    elif tool_name == "run_energy_analysis":
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

    # Approximate per-step timing (tool cycle elapsed since last tool completion).
    now_ms = time.perf_counter() * 1000.0
    baseline_ms = state.get("last_tool_ts_ms") or state.get("graph_started_at_ms") or now_ms
    elapsed_ms = max(1.0, now_ms - float(baseline_ms))
    step_durations = dict(state.get("step_durations_ms", {}))
    step_durations[tool_name] = float(step_durations.get(tool_name, 0.0)) + elapsed_ms
    updates["step_durations_ms"] = step_durations
    updates["last_tool_ts_ms"] = now_ms

    # Check for pipeline trigger emitted by run_energy_analysis.
    if isinstance(tool_result, dict) and "__trigger__" in tool_result:
        trigger = tool_result["__trigger__"]
        
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
                from agents.langgraph.tools import llm_energy_optimization_from_state
                tool_result = llm_energy_optimization_from_state(
                    request=state.get("request", {}),
                    perception=state.get("perception_result") or {},
                    spatial=state.get("spatial_result") or {},
                    satellite=state.get("satellite_result") or {},
                )
            elif trigger == "evidence_pack":
                from agents.langgraph.tools import llm_evidence_pack_from_state
                tool_result = llm_evidence_pack_from_state(
                    request=state.get("request", {}),
                    feature_context={
                        "perception": state.get("perception_result") or {},
                        "spatial": state.get("spatial_result") or {},
                        "satellite": state.get("satellite_result") or {},
                    },
                    optimization=state.get("energy_result") or {},
                )
            else:
                tool_result = {"status": "failed", "error": f"Unknown trigger: {trigger}"}
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
    history: list[dict] | None = None,
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

    started_at_ms = time.perf_counter() * 1000.0

    initial_messages: list = []
    if isinstance(history, list):
        for item in history[-24:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).strip().lower()
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            if role == "user":
                initial_messages.append(HumanMessage(content=content))
            elif role in {"assistant", "agent", "ai"}:
                initial_messages.append(AIMessage(content=content))
    if not initial_messages or str(getattr(initial_messages[-1], "content", "")).strip() != message.strip():
        initial_messages.append(HumanMessage(content=message))

    initial_state: AgentState = {
        "messages": initial_messages,
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
        "graph_started_at_ms": started_at_ms,
        "last_tool_ts_ms": None,
        "step_durations_ms": {},
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
    total_elapsed_ms = max(1.0, (time.perf_counter() * 1000.0) - started_at_ms)

    # Extract the final AI response
    last_ai_message = None
    for msg in reversed(final_state.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.content:
            last_ai_message = msg.content
            break

    return {
        "thread_id": config["configurable"]["thread_id"],
        "response": last_ai_message or "Analysis complete.",
        "history": [
            {"role": "user", "content": str(msg.content)}
            if isinstance(msg, HumanMessage)
            else {"role": "assistant", "content": str(msg.content)}
            for msg in final_state.get("messages", [])
            if isinstance(msg, (HumanMessage, AIMessage)) and getattr(msg, "content", None)
        ],
        "request": request,
        "perception_result": final_state.get("perception_result"),
        "spatial_result": final_state.get("spatial_result"),
        "satellite_result": final_state.get("satellite_result"),
        "energy_result": final_state.get("energy_result"),
        "evidence_result": final_state.get("evidence_result"),
        "completed_steps": final_state.get("completed_steps", []),
        "step_durations_ms": final_state.get("step_durations_ms", {}),
        "total_duration_ms": total_elapsed_ms,
        "errors": final_state.get("errors", []),
        "replan_reason": final_state.get("replan_reason"),
    }



