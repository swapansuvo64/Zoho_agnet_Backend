import json
import logging
from typing import TypedDict, Optional, Any
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage
from src.Config.model import llm
from src.Config.redis import get_redis, set_value, delete_value, get_value

# Import Action Tools
from src.tools.action.create_task import CreateTaskTool
from src.tools.action.update_task import UpdateTaskTool
from src.tools.action.delete_task import DeleteTaskTool
from src.tools.action.create_project import CreateProjectTool
from src.tools.action.update_project import UpdateProjectTool
from src.tools.action.delete_project import DeleteProjectTool

# Import Prompts
from src.agnets.prompt import ACTION_PARSING_PROMPT, get_action_explanation_prompt

logger = logging.getLogger("agent-service")

class ActionAgentState(TypedDict):
    # Inputs & Config
    operation: str  # "initiate" | "execute_pending"
    query: Optional[str]
    session_id: str
    access_token: Optional[str]
    approved: Optional[bool]
    stm_context: Optional[list[str]]
    ltm_context: Optional[list[dict]]   # cross-session vector DB results
    summary: Optional[str]
    
    # Internal & Outputs
    action: Optional[str]
    args: Optional[dict]
    clarification_needed: Optional[str]
    tool_result: Optional[dict]
    response: Optional[str]
    error: Optional[str]

# Node 1: Entry Router
async def entry_router_node(state: ActionAgentState) -> dict:
    # Retain the operation in state to satisfy LangGraph validation of entry updates
    return {"operation": state["operation"]}

def route_decision(state: ActionAgentState) -> str:
    if state["operation"] == "initiate":
        return "parse_action"
    elif state["operation"] == "execute_pending":
        return "load_and_run"
    return "explain"

# Node 2: Parse Action
async def parse_action_node(state: ActionAgentState) -> dict:
    query = state["query"]
    stm_context = state.get("stm_context") or []
    ltm_context = state.get("ltm_context") or []
    summary = state.get("summary") or ""
    
    # Format current summary, short-term, and long-term memory for the LLM
    from src.utils.date_utils import get_current_date_context
    context_str = get_current_date_context() + "\n\n"
    if summary:
        context_str += f"[Conversation entity details / Active project context]:\n{summary}\n\n"
    if stm_context:
        context_str += "[Recent Chat History — current session]:\n"
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
        SystemMessage(content=ACTION_PARSING_PROMPT),
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
            parsed = json.loads(resp_text)
            action = parsed.get("action")
            args = parsed.get("args", {}) or {}
            clarification_needed = parsed.get("clarification_needed")
            
            # --- Smart Auto-Resolution for Single Task Projects ---
            project_id = args.get("project_id")
            task_id = args.get("task_id")
            access_token = state.get("access_token")
            
            if (action in ("update_task", "delete_task")) and project_id and not task_id and access_token:
                try:
                    from src.tools.query.list_tasks import ListTasksTool
                    tasks_tool = ListTasksTool(access_token)
                    tasks_result = await tasks_tool.run(project_id)
                    if tasks_result.get("success") and tasks_result.get("tasks"):
                        tasks = tasks_result["tasks"]
                        # Filter only open/active tasks
                        open_tasks = [t for t in tasks if str(t.get("status_type", "")).lower() == "open" or not t.get("completed", False)]
                        target_tasks = open_tasks if open_tasks else tasks
                        
                        if len(target_tasks) == 1:
                            resolved_task = target_tasks[0]
                            args["task_id"] = str(resolved_task.get("id", ""))
                            if not args.get("name"):
                                args["name"] = resolved_task.get("name", "")
                            clarification_needed = None
                            logger.info(f"Auto-resolved single task '{resolved_task.get('name')}' ({resolved_task.get('id')}) for project {project_id}")
                except Exception as auto_err:
                    logger.error(f"Error in action auto-resolution: {str(auto_err)}")

            return {
                "action": action,
                "args": args,
                "clarification_needed": clarification_needed,
                "error": None
            }
        except Exception as parse_err:
            logger.error(f"Failed to parse Action routing JSON: {resp_text}. Error: {str(parse_err)}")
            return {"error": "I couldn't parse the internal write instructions. Could you please specify exactly what you want to do?"}
    except Exception as e:
        logger.error(f"Error in parse_action_node: {str(e)}")
        return {"error": f"An error occurred while preparing the task write operation: {str(e)}"}


# Node 3: Confirmation Prompt Builder
async def confirmation_prompt_node(state: ActionAgentState) -> dict:
    if state.get("error"):
        return {"response": state["error"]}
    if state.get("clarification_needed"):
        return {"response": state["clarification_needed"]}
        
    action = state["action"]
    args = state["args"] or {}
    session_id = state["session_id"]
    
    try:
        # Cache the parsed action details in Redis as "pending" for 5 minutes (300 seconds)
        redis = await get_redis()
        redis_key = f"pending_action:{session_id}"
        
        cache_payload = {
            "action": action,
            "args": args
        }
        await set_value(redis, redis_key, json.dumps(cache_payload), 300)
        
        # Generate a gorgeous confirmation card
        action_labels = {
            "create_project": "Create Project",
            "update_project": "Update Project",
            "delete_project": "Delete Project",
            "create_task": "Create Task",
            "update_task": "Update Task",
            "delete_task": "Delete Task"
        }
        label = action_labels.get(action, "Zoho Action")
        
        args_details = []
        for k, v in args.items():
            if v:
                args_details.append(f"- **{k.replace('_', ' ').title()}**: `{v}`")
                
        args_formatted = "\n".join(args_details)

        confirmation_prompt = f"""### ⚠️ Human-in-the-Loop Confirmation Required

I have prepared the following write operation on Zoho Projects and need your approval to proceed:

*   **Operation**: {label}
{args_formatted}

***

**Do you want to proceed?**
- Reply **"Yes"** or **"Confirm"** to execute.
- Reply **"No"** or **"Cancel"** to abort.
"""
        return {"response": confirmation_prompt}
    except Exception as e:
        logger.error(f"Error in confirmation_prompt_node: {str(e)}")
        return {"response": f"An error occurred while saving the pending action: {str(e)}"}

# Node 4: Load and Run Pending Action
async def load_and_run_node(state: ActionAgentState) -> dict:
    session_id = state["session_id"]
    access_token = state["access_token"]
    approved = state["approved"]
    
    redis = await get_redis()
    redis_key = f"pending_action:{session_id}"
    
    cached = await get_value(redis, redis_key)
    if not cached:
        return {"response": "No pending action found to confirm or cancel. How can I help you today?"}
        
    # Clean up Redis state
    await delete_value(redis, redis_key)
    
    if not approved:
        return {"response": "❌ **Action Aborted.** The pending write operation has been canceled cleanly with no changes made to Zoho Projects."}
        
    try:
        parsed = json.loads(cached)
        action = parsed.get("action")
        args = parsed.get("args", {}) or {}
        
        project_id = args.get("project_id")
        task_id = args.get("task_id")
        name = args.get("name")
        description = args.get("description")
        person_responsible = args.get("person_responsible")
        start_date = args.get("start_date")
        end_date = args.get("end_date")
        status = args.get("status")
        
        result = None
        logger.info(f"Executing pending Zoho action '{action}' with args: {args}")
        
        if action == "create_project":
            tool = CreateProjectTool(access_token)
            result = await tool.run(
                name=name,
                description=description,
                start_date=start_date,
                end_date=end_date
            )
        elif action == "update_project":
            tool = UpdateProjectTool(access_token)
            result = await tool.run(
                project_id=project_id,
                name=name,
                description=description,
                start_date=start_date,
                end_date=end_date,
                status=status
            )
        elif action == "delete_project":
            tool = DeleteProjectTool(access_token)
            result = await tool.run(project_id=project_id)
        elif action == "create_task":
            tool = CreateTaskTool(access_token)
            result = await tool.run(
                project_id=project_id,
                name=name,
                description=description,
                person_responsible=person_responsible,
                start_date=start_date,
                end_date=end_date
            )
        elif action == "update_task":
            tool = UpdateTaskTool(access_token)
            result = await tool.run(
                project_id=project_id,
                task_id=task_id,
                name=name,
                description=description,
                person_responsible=person_responsible,
                start_date=start_date,
                end_date=end_date,
                status=status
            )
        elif action == "delete_task":
            tool = DeleteTaskTool(access_token)
            result = await tool.run(project_id=project_id, task_id=task_id)
        else:
            return {"error": "Unknown pending action type."}

        if not result or not result.get("success"):
            err = result.get("error", "Unknown Zoho Projects write failure") if result else "No response"
            return {"error": f"❌ **Execution Failed:** {err}"}
            
        return {"action": action, "tool_result": result}
    except Exception as e:
        logger.error(f"Error in load_and_run_node: {str(e)}")
        return {"error": f"An error occurred while executing the pending action: {str(e)}"}

# Node 5: Explain Write Node
async def explain_action_node(state: ActionAgentState) -> dict:
    if state.get("error"):
        return {"response": state["error"]}
    if state.get("response"): # e.g. aborted
        return {}
        
    action = state["action"]
    tool_result = state["tool_result"]
    
    explanation_prompt = get_action_explanation_prompt(action, json.dumps(tool_result, indent=2))
    try:
        explanation_messages = [
            SystemMessage(content=explanation_prompt),
            HumanMessage(content="Please format and explain the Zoho Projects action execution success according to your instructions.")
        ]
        explanation_resp = await llm.ainvoke(explanation_messages)
        return {"response": f"✅ **Success!**\n\n{explanation_resp.content}"}
    except Exception as e:
        logger.error(f"Error in explain_action_node: {str(e)}")
        return {"response": f"✅ **Success!** (Failed to format confirmation message, raw details: {json.dumps(tool_result)})"}

# Build Action Graph with Nodes in Loop style
workflow = StateGraph(ActionAgentState)
workflow.add_node("entry_router", entry_router_node)
workflow.add_node("parse_action", parse_action_node)
workflow.add_node("confirmation_prompt", confirmation_prompt_node)
workflow.add_node("load_and_run", load_and_run_node)
workflow.add_node("explain_action", explain_action_node)

workflow.set_entry_point("entry_router")

workflow.add_conditional_edges(
    "entry_router",
    route_decision,
    {
        "parse_action": "parse_action",
        "load_and_run": "load_and_run",
        "explain_action": "explain_action"
    }
)

workflow.add_edge("parse_action", "confirmation_prompt")
workflow.add_edge("confirmation_prompt", END)
workflow.add_edge("load_and_run", "explain_action")
workflow.add_edge("explain_action", END)

action_graph = workflow.compile()

class ActionAgent:
    """
    ActionAgent handles all Zoho Project write operations (create/update/delete tasks).
    Features Human-in-the-Loop workflow implemented as a LangGraph StateGraph.
    """
    async def initiate_action(self, query: str, session_id: str, stm_context: list = None, summary: str = None) -> str:
        """
        Parses intent and arguments from the user query, caches it as a pending action,
        and outputs a confirmation prompt.
        """
        initial_state = {
            "operation": "initiate",
            "query": query,
            "session_id": session_id,
            "access_token": None,
            "approved": None,
            "action": None,
            "args": None,
            "clarification_needed": None,
            "tool_result": None,
            "response": None,
            "error": None,
            "stm_context": stm_context or [],
            "summary": summary or ""
        }
        try:
            final_state = await action_graph.ainvoke(initial_state)
            return final_state.get("response") or "Failed to initiate action."
        except Exception as e:
            logger.error(f"Error initiating action via LangGraph: {str(e)}")
            return f"An error occurred while preparing the task write operation: {str(e)}"

    async def execute_pending_action(self, session_id: str, access_token: str, approved: bool) -> str:
        """
        Executes or aborts the pending action saved in Redis based on user decision.
        """
        initial_state = {
            "operation": "execute_pending",
            "query": None,
            "session_id": session_id,
            "access_token": access_token,
            "approved": approved,
            "action": None,
            "args": None,
            "clarification_needed": None,
            "tool_result": None,
            "response": None,
            "error": None
        }
        try:
            final_state = await action_graph.ainvoke(initial_state)
            return final_state.get("response") or "Failed to execute pending action."
        except Exception as e:
            logger.error(f"Error executing pending action via LangGraph: {str(e)}")
            return f"An error occurred while executing the pending action: {str(e)}"

action_agent = ActionAgent()
