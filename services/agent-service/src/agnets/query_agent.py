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
from src.tools.query.get_task_comments import GetTaskCommentsTool

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
    stm_context: Optional[list[str]]
    ltm_context: Optional[list[dict]]   # cross-session vector DB results
    summary: Optional[str]
    user_info: Optional[dict]
    chrono_context: Optional[str]

# Node 1: Router Node
async def route_query_node(state: QueryAgentState) -> dict:
    query = state["query"]
    stm_context = state.get("stm_context") or []
    ltm_context = state.get("ltm_context") or []
    summary = state.get("summary") or ""
    user_info = state.get("user_info") or {}
    chrono_context = state.get("chrono_context") or ""
    
    # Format current summary, short-term chat context, and long-term memory for the LLM
    from src.utils.date_utils import get_current_date_context
    context_str = get_current_date_context() + "\n\n"
    if user_info:
        name = user_info.get("name")
        email = user_info.get("email")
        context_str += f"[Logged-in User Details]:\nName: {name or 'N/A'}, Email: {email or 'N/A'}\n\n"
    if summary:
        context_str += f"[Conversation entity details / Active project context]:\n{summary}\n\n"
    if chrono_context:
        context_str += f"[Current Session History (Chronological — Recent Turns)]:\n{chrono_context}\n\n"
    if stm_context:
        context_str += "[Recent Chat History — current session (Semantic matches)]:\n"
        context_str += "\n".join(stm_context) + "\n\n"
    if ltm_context:
        ltm_lines = []
        for item in ltm_context:
            text = item.get("text", "")
            meta = item.get("metadata", {}) or {}
            role = meta.get("role", "")
            sid  = meta.get("session_id", "")
            m_type = meta.get("type", "message")
            if m_type == "summary":
                ltm_lines.append(f"- [Past session summary (session {sid})]: {text}")
            else:
                prefix = f" ({role})" if role else ""
                ltm_lines.append(f"- [Past message{prefix} (session {sid})]: {text}")
        if ltm_lines:
            context_str += "[Long-term memory — past sessions, semantically relevant]:\n"
            context_str += "\n".join(ltm_lines) + "\n\n"

    messages = [
        SystemMessage(content=QUERY_ROUTING_PROMPT),
        HumanMessage(content=f"{context_str}User Query: {query}")
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
        elif tool_name == "get_task_comments":
            if not project_id or not task_id:
                return {"error": "Both Project ID and Task ID are required to fetch comments."}
            tool = GetTaskCommentsTool(access_token)
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
        messages = [
            SystemMessage(content=explanation_prompt),
            HumanMessage(content="Please format and explain the Zoho Projects query results above according to your instructions.")
        ]
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
    async def process_query(self, query: str, access_token: str, stm_context: list = None, ltm_context: list = None, summary: str = None, user_info: dict = None, chrono_context: str = None) -> str:
        initial_state = {
            "query": query,
            "access_token": access_token,
            "tool": None,
            "args": None,
            "clarification_needed": None,
            "tool_result": None,
            "response": None,
            "error": None,
            "stm_context": stm_context or [],
            "ltm_context": ltm_context or [],
            "summary": summary or "",
            "user_info": user_info,
            "chrono_context": chrono_context or ""
        }
        try:
            final_state = await query_graph.ainvoke(initial_state)
            return final_state.get("response") or "No response could be generated."
        except Exception as e:
            logger.error(f"Error running QueryAgent LangGraph: {str(e)}")
            return f"An error occurred while executing the query workflow: {str(e)}"

query_agent = QueryAgent()

