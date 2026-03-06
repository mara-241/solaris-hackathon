import json
import logging
from agents.langgraph.graph import run_solaris_graph

logging.basicConfig(level=logging.INFO)

print("\n--- Test 1 Pipeline: Chat ---")
res1 = run_solaris_graph(
    message="Hello, how are you?",
    lat=1.29,
    lon=36.82,
    households=100,
    horizon_days=30
)
print("Response:", res1["response"])
print("Completed Steps:", res1["completed_steps"])
assert "run_energy_analysis" not in res1["completed_steps"]

print("\n--- Test 2 Pipeline: Analysis ---")
res2 = run_solaris_graph(
    message="Generate an energy plan for Nairobi",
    lat=1.29,
    lon=36.82,
    households=100,
    horizon_days=30
)
print("Response:", res2["response"])
print("Completed Steps:", res2["completed_steps"])
assert "run_energy_analysis" in res2["completed_steps"] or "perception_data" in res2["completed_steps"]

print("\nAll tests passed!")
