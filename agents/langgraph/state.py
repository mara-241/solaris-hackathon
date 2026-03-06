"""
LangGraph state schema for the Solaris agentic supervisor.

Defines the typed state dictionary that flows through the graph.
"""

from __future__ import annotations

from typing import Annotated, Any

from langgraph.graph.message import add_messages


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class SolarisState(dict):
    """
    State passed through the LangGraph supervisor graph.

    Fields
    ------
    messages : list
        Conversation history using LangGraph's ``add_messages`` reducer so
        that successive invocations automatically append rather than replace.
    request : dict
        Original user request (lat, lon, households, horizon_days, …).
    perception_result : dict | None
        Output of the Perception agent (weather, demographics, hazards).
    spatial_result : dict | None
        Output of the Spatial VLM agent (NDVI, buildings, density).
    satellite_result : dict | None
        Output of the Satellite Imagery tool (Sentinel-2 analytics).
    energy_result : dict | None
        Output of the Energy Optimization agent.
    evidence_result : dict | None
        Output of the Evidence Pack builder.
    plan : list[str]
        The supervisor's current plan — an ordered list of tool names to
        call.  Updated by the replanner when dynamic replanning occurs.
    replan_reason : str | None
        Human-readable reason the last replan happened (e.g. *"cloud
        cover 45 % > threshold 30 %"*).
    completed_steps : list[str]
        Tool names that have already been executed.
    errors : list[str]
        Error messages accumulated during execution.
    """
    pass


# Type hints used by LangGraph's StateGraph
SOLARIS_STATE_SCHEMA: dict[str, Any] = {
    "messages": Annotated[list, add_messages],
    "request": dict,
    "perception_result": dict | None,
    "spatial_result": dict | None,
    "satellite_result": dict | None,
    "energy_result": dict | None,
    "evidence_result": dict | None,
    "plan": list,
    "replan_reason": str | None,
    "completed_steps": list,
    "errors": list,
}
