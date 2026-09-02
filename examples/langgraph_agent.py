"""Drive the stampede swarm with your own LangGraph agent (v0.3, NG-3-respecting).

stampede owns the population (personas, goals), the target, chaos, and the report;
YOUR agent makes each tool decision. You provide a ``graph_factory(tools)`` that
returns a compiled LangGraph react agent bound to ``tools`` — stampede passes it
capture-stub tools, runs your graph per agent, and records what it chose.

    pip install "stampede[langgraph,providers]" langgraph
    # in stampede.yaml:
    #   population:
    #     framework: langgraph
    #     framework_ref: "examples.langgraph_agent:graph_factory"
    #     models: [ollama:llama3.1]     # the model your agent uses
    #   report: { budget_usd: 2.00 }
    # then a LIVE run (no --dry-run):
    #   stampede run
"""

from __future__ import annotations

from typing import Any


def graph_factory(tools: list[Any]):
    """Return a compiled LangGraph react agent bound to ``tools``.

    Swap the model for whatever your agent uses. The tools stampede passes are
    capture stubs — your agent's *choices* are measured; stampede executes the real
    calls on the target."""
    from langchain_openai import ChatOpenAI  # or ChatAnthropic, ChatOllama, …
    from langgraph.prebuilt import create_react_agent

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    return create_react_agent(llm, tools)
