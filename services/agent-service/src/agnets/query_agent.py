import json
import logging
from typing import TypedDict, Optional, Any
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage
from src.Config.model import llm
from src.agnets.prompt import QUERY_ROUTING_PROMPT, get_query_explanation_prompt

# Import all tools
from src.tools.query.list_projects import ListProjectsTool
from src.tools.query.list_tasks import ListTasksTool
from src.tools.query.get_task_details import GetTaskDetailsTool
from src.tools.query.list_project_members import ListProjectMembersTool
from src.tools.query.get_task_utilisation import GetTaskUtilisationTool

logger = logging.getLogger("agent-service")

class QueryAgentState(TypedDict):
    query: str
    access_token: str
    tool: Optional[str]
    args: Optional[dict]
    clarification_needed: Optional[str]
    tool_result: Optional[dict]
    response: Optional[str]
    error: Optional[str]

# Node 1: Router Node
async def route_query_node(state: QueryAgentState) -> dict:
    query = state["query"]
    messages = [
        SystemMessage(content=QUERY_ROUTING_PROMPT),
        HumanMessage(content=f"User Query: {query}")
    ]
    try:
        resp = await llm.ainvoke(messages)
        resp_text = resp.content.strip()
        
        # Clean up response markdown blocks if present
        if resp_text.startswith("```json"):
            resp_text = resp_text[7:]
        elif resp_text.startswith("```"):
            resp_text = resp_text[3:]
        if resp_text.endswith("```"):
            resp_text = resp_text[:-3]
        resp_text = resp_text.strip()
        
        try:
            routing = json.loads(resp_text)
            return {
                "tool": routing.get("tool"),
                "args": routing.get("args", {}) or {},
                "clarification_needed": routing.get("clarification_needed"),
                "error": None
            }
        except Exception as parse_err:
            logger.error(f"Failed to parse Query routing JSON: {resp_text}. Error: {str(parse_err)}")
            return {"error": "I couldn't parse the internal routing instructions. Could you please rephrase your request?"}
    except Exception as e:
        logger.error(f"Error in route_query_node: {str(e)}")
        return {"error": f"An error occurred during query analysis: {str(e)}"}

# Conditional edge logic
def router_decision(state: QueryAgentState) -> str:
    if state.get("error"):
        return "explain"
    if state.get("clarification_needed"):
        return "explain"
    if state.get("tool"):
        return "execute_tool"
    return "explain"

# Node 2: Tool Execution Node
async def execute_tool_node(state: QueryAgentState) -> dict:
    tool_name = state["tool"]
    args = state["args"] or {}
    access_token = state["access_token"]
    
    project_id = args.get("project_id")
    task_id = args.get("task_id")
    
    result = None
    try:
        if tool_name == "list_projects":
            tool = ListProjectsTool(access_token)
            result = await tool.run()
        elif tool_name == "list_tasks":
            if not project_id:
                return {"error": "Which project would you like to list the tasks for? Please provide a Project ID."}
            tool = ListTasksTool(access_token)
            result = await tool.run(project_id)
        elif tool_name == "get_task_details":
            if not project_id or not task_id:
                return {"error": "Both Project ID and Task ID are required to fetch task details."}
            tool = GetTaskDetailsTool(access_token)
            result = await tool.run(project_id, task_id)
        elif tool_name == "list_project_members":
            if not project_id:
                return {"error": "Please specify a Project ID to fetch its member list."}
            tool = ListProjectMembersTool(access_token)
            result = await tool.run(project_id)
        elif tool_name == "get_task_utilisation":
            if not project_id or not task_id:
                return {"error": "Both Project ID and Task ID are required to fetch resource logs."}
            tool = GetTaskUtilisationTool(access_token)
            result = await tool.run(project_id, task_id)
        else:
            return {"error": "I couldn't identify the correct query tool. Could you please verify your request?"}
            
        if not result or not result.get("success"):
            err = result.get("error", "Unknown Zoho Projects API error") if result else "No response"
            return {"error": f"Zoho Projects API query failed: {err}"}
            
        return {"tool_result": result}
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {str(e)}")
        return {"error": f"An error occurred while executing the tool: {str(e)}"}

# Node 3: Explainer Node
async def explain_node(state: QueryAgentState) -> dict:
    if state.get("error"):
        return {"response": state["error"]}
    if state.get("clarification_needed"):
        return {"response": state["clarification_needed"]}
        
    query = state["query"]
    tool_name = state["tool"]
    tool_result = state["tool_result"]
    
    explanation_prompt = get_query_explanation_prompt(query, tool_name, json.dumps(tool_result, indent=2))
    
    try:
        messages = [SystemMessage(content=explanation_prompt)]
        explanation_resp = await llm.ainvoke(messages)
        return {"response": explanation_resp.content}
    except Exception as e:
        logger.error(f"Error in explain_node: {str(e)}")
        return {"response": f"Successfully queried Zoho, but failed to format the response. Raw details: {json.dumps(tool_result)}"}

# Build Query Graph with Nodes in Loop style
workflow = StateGraph(QueryAgentState)
workflow.add_node("route_query", route_query_node)
workflow.add_node("execute_tool", execute_tool_node)
workflow.add_node("explain", explain_node)

workflow.set_entry_point("route_query")
workflow.add_conditional_edges(
    "route_query",
    router_decision,
    {
        "execute_tool": "execute_tool",
        "explain": "explain"
    }
)
workflow.add_edge("execute_tool", "explain")
workflow.add_edge("explain", END)

query_graph = workflow.compile()

class QueryAgent:
    """
    QueryAgent handles all Zoho Project read requests.
    Implemented as a LangGraph StateGraph pipeline.
    """
    async def process_query(self, query: str, access_token: str) -> str:
        initial_state = {
            "query": query,
            "access_token": access_token,
            "tool": None,
            "args": None,
            "clarification_needed": None,
            "tool_result": None,
            "response": None,
            "error": None
        }
        try:
            final_state = await query_graph.ainvoke(initial_state)
            return final_state.get("response") or "No response could be generated."
        except Exception as e:
            logger.error(f"Error running QueryAgent LangGraph: {str(e)}")
            return f"An error occurred while executing the query workflow: {str(e)}"

query_agent = QueryAgent()
