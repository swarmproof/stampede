"""Drive the stampede swarm with your own CrewAI crew (v0.3, NG-3-respecting).

You provide a ``crew_factory(tools, goal)`` returning a Crew whose agent is bound to
``tools`` and tasked with ``goal``. stampede passes capture-stub tools, kicks off
your crew per swarm agent, and records which tool it chose — your crew's *decision*
is measured while stampede executes the real call on the target.

    pip install "stampede[crewai]" crewai
    # in stampede.yaml:
    #   population:
    #     framework: crewai
    #     framework_ref: "examples.crewai_agent:crew_factory"
    #   report: { budget_usd: 2.00 }
    # then a LIVE run (no --dry-run):  stampede run
"""

from __future__ import annotations

from typing import Any


def crew_factory(tools: list[Any], goal: str) -> Any:
    """Return a CrewAI Crew whose agent pursues ``goal`` with ``tools``."""
    from crewai import Agent, Crew, Task

    operator = Agent(
        role="Operator",
        goal="Use the available tools to accomplish the task.",
        backstory="A careful operator driving an unfamiliar system.",
        tools=tools,  # stampede's capture stubs (CrewAI accepts LangChain tools)
    )
    task = Task(description=goal, agent=operator, expected_output="the tool result")
    return Crew(agents=[operator], tasks=[task])
