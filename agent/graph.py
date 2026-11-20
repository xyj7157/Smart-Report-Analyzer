from langgraph.graph import StateGraph, START, END
from agent.state import AgentState
from agent.nodes import (
    extract_data_node, calculate_node, search_competitor_node,
    summary_node, save_to_db_node
)

workflow = StateGraph(AgentState)
workflow.add_node("extract", extract_data_node)
workflow.add_node("calculate", calculate_node)
workflow.add_node("search_competitor", search_competitor_node)
workflow.add_node("summary", summary_node)
workflow.add_node("save_to_db", save_to_db_node)

workflow.add_edge(START, "extract")
workflow.add_edge("extract", "calculate")
workflow.add_edge("calculate", "search_competitor")
workflow.add_edge("search_competitor", "summary")
workflow.add_edge("summary", "save_to_db")
workflow.add_edge("save_to_db", END)

agent_graph = workflow.compile()