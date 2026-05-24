import json
import logging
import asyncio
from src.Config.model import llm
from src.Config.redis import get_redis, set_value, delete_value, get_value
from langchain_core.messages import SystemMessage, HumanMessage

# Import Tools
from src.tools.query.list_projects import ListProjectsTool
from src.tools.query.list_tasks import ListTasksTool
from src.tools.query.list_project_members import ListProjectMembersTool
from src.tools.query.get_task_details import GetTaskDetailsTool
from src.tools.query.get_task_utilisation import GetTaskUtilisationTool
from src.tools.query.get_task_comments import GetTaskCommentsTool

from src.tools.action.create_task import CreateTaskTool
from src.tools.action.update_task import UpdateTaskTool
from src.tools.action.delete_task import DeleteTaskTool
from src.tools.action.create_project import CreateProjectTool
from src.tools.action.update_project import UpdateProjectTool
from src.tools.action.delete_project import DeleteProjectTool
from src.tools.action.add_task_comment import AddTaskCommentTool

# Import Prompts
from src.agnets.prompt import GENERAL_ORCHESTRATOR_PROMPT

logger = logging.getLogger("agent-service")

# Map of available query tools
QUERY_TOOLS = {
    "list_projects": ListProjectsTool,
    "list_tasks": ListTasksTool,
    "list_project_members": ListProjectMembersTool,
    "get_task_details": GetTaskDetailsTool,
    "get_task_utilisation": GetTaskUtilisationTool,
    "get_task_comments": GetTaskCommentsTool
}

async def run_single_action(access_token: str, action_data: dict) -> dict:
    action = action_data["action"]
    args = action_data["args"] or {}
    
    project_id = args.get("project_id")
    task_id = args.get("task_id")
    name = args.get("name")
    description = args.get("description")
    person_responsible = args.get("person_responsible")
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    status = args.get("status")
    
    try:
        if action == "create_project":
            tool = CreateProjectTool(access_token)
            res = await tool.run(
                name=name,
                description=description,
                start_date=start_date,
                end_date=end_date
            )
            return {"action": action, "args": args, "result": res}
        elif action == "update_project":
            tool = UpdateProjectTool(access_token)
            res = await tool.run(
                project_id=project_id,
                name=name,
                description=description,
                start_date=start_date,
                end_date=end_date,
                status=status
            )
            return {"action": action, "args": args, "result": res}
        elif action == "delete_project":
            tool = DeleteProjectTool(access_token)
            res = await tool.run(project_id=project_id)
            return {"action": action, "args": args, "result": res}
        elif action == "create_task":
            tool = CreateTaskTool(access_token)
            res = await tool.run(
                project_id=project_id,
                name=name,
                description=description,
                person_responsible=person_responsible,
                start_date=start_date,
                end_date=end_date
            )
            return {"action": action, "args": args, "result": res}
        elif action == "update_task":
            tool = UpdateTaskTool(access_token)
            res = await tool.run(
                project_id=project_id,
                task_id=task_id,
                name=name,
                description=description,
                person_responsible=person_responsible,
                start_date=start_date,
                end_date=end_date,
                status=status
            )
            return {"action": action, "args": args, "result": res}
        elif action == "delete_task":
            tool = DeleteTaskTool(access_token)
            res = await tool.run(project_id=project_id, task_id=task_id)
            return {"action": action, "args": args, "result": res}
        elif action == "add_task_comment":
            tool = AddTaskCommentTool(access_token)
            res = await tool.run(
                project_id=project_id,
                task_id=task_id,
                content=args.get("content")
            )
            return {"action": action, "args": args, "result": res}
        else:
            return {"action": action, "args": args, "result": {"success": False, "error": "Unknown action type"}}
    except Exception as e:
        return {"action": action, "args": args, "result": {"success": False, "error": str(e)}}


class OrchestratorAgent:
    """
    OrchestratorAgent coordinates multi-step retrieval, filtering, and bulk operations.
    Implements an autonomous ReAct loop that executes any query tools iteratively
    to gather context and plans write actions dynamically until fulfillment.
    """
    async def initiate_orchestration(
        self,
        query: str,
        session_id: str,
        access_token: str,
        stm_context: list[str] = None,
        summary: str = None,
        chrono_context: str = None
    ) -> str:
        # Format current context
        from src.utils.date_utils import get_current_date_context
        context_str = get_current_date_context() + "\n\n"
        if summary:
            context_str += f"[Conversation entity details / Active project context]:\n{summary}\n\n"
        if chrono_context:
            context_str += f"[Current Session History (Chronological — Recent Turns)]:\n{chrono_context}\n\n"
        if stm_context:
            context_str += "[Recent Chat History context — Semantic matches]:\n"
            context_str += "\n".join(stm_context) + "\n\n"

        history = []
        max_iterations = 6
        
        for iteration in range(max_iterations):
            logger.info(f"Orchestrator ReAct Iteration {iteration+1}/{max_iterations}")
            
            # Build current agent context including tools history
            history_str = ""
            if history:
                history_str += "Tools Executed So Far:\n"
                for step in history:
                    history_str += f"- Step {step['step']}: Called '{step['tool']}' with args {step['args']}.\n  Result: {json.dumps(step['result'])}\n\n"
            else:
                history_str = "No tools executed yet in this planning turn.\n"
                
            messages = [
                SystemMessage(content=GENERAL_ORCHESTRATOR_PROMPT),
                HumanMessage(content=f"[Current Conversation Context]:\n{context_str}\n\n{history_str}\nUser Query: {query}")
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
                
                decision_payload = json.loads(resp_text)
            except Exception as parse_err:
                logger.error(f"Failed to parse Orchestrator ReAct JSON: {resp_text}. Error: {str(parse_err)}")
                return "I encountered an error planning the multi-agent task execution. Could you please rephrase your request?"

            thought = decision_payload.get("thought", "")
            decision = decision_payload.get("decision", "finish")
            
            logger.info(f"Orchestrator Thought: {thought}")
            logger.info(f"Orchestrator Decision: {decision}")

            # ── Option 1: Call a QUERY Tool ──
            if decision == "call_query":
                query_tool_data = decision_payload.get("query_tool") or {}
                tool_name = query_tool_data.get("name")
                tool_args = query_tool_data.get("args") or {}
                
                if tool_name not in QUERY_TOOLS:
                    logger.error(f"Orchestrator planned unknown tool: {tool_name}")
                    return f"❌ Agent planning error: Unknown query tool '{tool_name}' requested."
                
                logger.info(f"Executing query tool '{tool_name}' with args: {tool_args}")
                
                # Instantiate and run query tool
                tool_class = QUERY_TOOLS[tool_name]
                tool_instance = tool_class(access_token)
                
                # Determine parameters dynamically
                try:
                    if tool_name == "list_projects":
                        result = await tool_instance.run()
                    elif tool_name == "list_project_members":
                        result = await tool_instance.run(project_id=tool_args.get("project_id"))
                    elif tool_name == "list_tasks":
                        result = await tool_instance.run(project_id=tool_args.get("project_id"))
                    elif tool_name == "get_task_details":
                        result = await tool_instance.run(project_id=tool_args.get("project_id"), task_id=tool_args.get("task_id"))
                    elif tool_name == "get_task_utilisation":
                        result = await tool_instance.run(project_id=tool_args.get("project_id"), task_id=tool_args.get("task_id"))
                    elif tool_name == "get_task_comments":
                        result = await tool_instance.run(project_id=tool_args.get("project_id"), task_id=tool_args.get("task_id"))
                    else:
                        result = {"success": False, "error": "Unknown tool invocation"}
                except Exception as run_err:
                    logger.error(f"Error running query tool {tool_name}: {str(run_err)}")
                    result = {"success": False, "error": str(run_err)}

                # Add to history context
                history.append({
                    "step": iteration + 1,
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result
                })
                continue
                
            # ── Option 2: Plan WRITE Actions (Human-in-the-Loop) ──
            elif decision == "plan_write":
                actions = decision_payload.get("write_actions", [])
                plan_desc = decision_payload.get("plan_description", "Batch updates prepared.")
                
                if not actions:
                    return "🔍 Scanning complete: No write actions were planned."
                
                # Cache proposed write actions in Redis as a batch
                redis = await get_redis()
                redis_key = f"pending_actions:{session_id}"
                
                # Resolve primary project ID from the first action or query history
                project_id = None
                for act in actions:
                    project_id = act.get("args", {}).get("project_id")
                    if project_id:
                        break
                
                # Build user ID to name map from ReAct history
                user_id_to_name = {}
                for step in history:
                    if step.get("tool") == "list_project_members":
                        members_list = step.get("result", {}).get("members", [])
                        for m in members_list:
                            m_id = m.get("id")
                            m_zpuid = m.get("zpuid")
                            m_name = m.get("name")
                            if m_id and m_name:
                                user_id_to_name[str(m_id)] = m_name
                            if m_zpuid and m_name:
                                user_id_to_name[str(m_zpuid)] = m_name

                cache_payload = {
                    "project_id": project_id,
                    "actions": actions,
                    "user_id_to_name": user_id_to_name
                }
                await set_value(redis, redis_key, json.dumps(cache_payload), 300) # 5 minutes TTL
                
                # Render beautiful Confirmation Card with clickable links
                confirmation_details = []
                action_labels = {
                    "create_project": "Create Project",
                    "update_project": "Update Project",
                    "delete_project": "Delete Project",
                    "create_task": "Create Task",
                    "update_task": "Update Task",
                    "delete_task": "Delete Task",
                    "add_task_comment": "Add Comment"
                }
                
                for idx, act in enumerate(actions, 1):
                    args = act["args"] or {}
                    act_type = act["action"]
                    label = action_labels.get(act_type, "Update")
                    t_name = args.get("name") or "Task"
                    t_id = args.get("task_id")
                    p_id = args.get("project_id") or project_id
                    
                    # Create interactive deep link
                    t_link = f"[{t_name}](task://{p_id}/{t_id})" if t_id else f"[{t_name}](project://{p_id})" if p_id else t_name
                    
                    mod_details = []
                    for k, v in args.items():
                        if k not in ("project_id", "task_id", "name") and v:
                            mod_details.append(f"  - **{k.replace('_', ' ').title()}**: `{v}`")
                    
                    mod_str = "\n".join(mod_details)
                    confirmation_details.append(f"{idx}. **{label}**: {t_link}\n{mod_str}")
                    
                args_formatted = "\n".join(confirmation_details)
                
                confirmation_prompt = f"""### ⚠️ Human-in-the-Loop Confirmation Required
                
{plan_desc}

I have prepared the following **{len(actions)}** multi-task operations on Zoho Projects:

{args_formatted}

***

**Do you want to proceed with executing these updates in parallel?**
- Reply **"Yes"** or **"Confirm"** to execute.
- Reply **"No"** or **"Cancel"** to abort.
"""
                return confirmation_prompt
                
            # ── Option 3: Finish (Conversational / Read-Only Response) ──
            elif decision == "finish":
                final_response = decision_payload.get("final_response", "")
                if not final_response:
                    final_response = "I have successfully analyzed the data. No write actions are required."
                return final_response
                
        # If we exceeded max_iterations
        return "⚠️ I attempted to complete your request, but it required too many sequential steps. Could you please be more specific or break down your instructions?"

    async def execute_pending_actions(self, session_id: str, access_token: str, approved: bool) -> str:
        redis = await get_redis()
        redis_key = f"pending_actions:{session_id}"
        
        cached = await get_value(redis, redis_key)
        if not cached:
            return "No pending multi-task updates found to confirm or cancel. How can I help you today?"
            
        # Clean up Redis state
        await delete_value(redis, redis_key)
        
        if not approved:
            return "❌ **Action Aborted.** The pending multi-task write operations have been canceled cleanly."
            
        try:
            payload = json.loads(cached)
            project_id = payload.get("project_id")
            actions = payload.get("actions", [])
            user_id_to_name = payload.get("user_id_to_name") or {}
            
            logger.info(f"Executing {len(actions)} pending orchestrated updates in parallel...")
            
            # Run all operations concurrently using asyncio.gather
            tasks_to_run = [run_single_action(access_token, act) for act in actions]
            results = await asyncio.gather(*tasks_to_run, return_exceptions=True)
            
            # Synthesize final result summary report
            success_count = 0
            fail_count = 0
            report_lines = []
            
            for res in results:
                if isinstance(res, Exception):
                    fail_count += 1
                    report_lines.append(f"| N/A | ❌ Error | Internal task run failed: {str(res)} |")
                    continue
                    
                args = res["args"]
                act_type = res["action"]
                run_res = res["result"] or {}
                
                t_name = args.get("name") or ("Project" if "project" in act_type else "Task")
                # Robustly resolve newly created or updated task ID from nested tool response
                t_id = args.get("task_id") or run_res.get("task_id") or run_res.get("task", {}).get("id")
                p_id = args.get("project_id") or run_res.get("project_id") or project_id
                
                if t_id:
                    t_link = f"[{t_name}](task://{p_id}/{t_id})"
                elif p_id:
                    t_link = f"[{t_name}](project://{p_id})"
                else:
                    t_link = t_name
                
                if run_res.get("success"):
                    success_count += 1
                    updates = []
                    for k, v in args.items():
                        if k not in ("project_id", "task_id", "name") and v:
                            label_key = k.replace('_', ' ').title()
                            val_str = str(v)
                            # Translate assignee user ID to name if present
                            if k == "person_responsible" and val_str in user_id_to_name:
                                val_str = user_id_to_name[val_str]
                            updates.append(f"**{label_key}**: `{val_str}`")
                    update_str = ", ".join(updates) if updates else "Executed successfully"
                    report_lines.append(f"| {t_link} | ✅ Success | {update_str} |")
                else:
                    fail_count += 1
                    err_msg = run_res.get("error", "Zoho API error")
                    report_lines.append(f"| {t_link} | ❌ Failed | {err_msg} |")
            
            report_table = "\n".join(report_lines)
            
            # Explicitly format the markdown table to have zero indentation and proper spacing
            final_report = (
                f"### ✅ Batch Execution Report\n\n"
                f"I have executed **{len(actions)}** write operations in parallel on Zoho Projects. Here is the summary:\n\n"
                f"*   **Successfully Updated**: {success_count} task(s)\n"
                f"*   **Failed**: {fail_count} task(s)\n\n"
                f"| Task Link | Execution Status | Updates Made / Error Message |\n"
                f"| --- | --- | --- |\n"
                f"{report_table}\n\n"
                f"***\n"
                f"You can click on any updated task name to open its interactive detail popup modal with comprehensive allocations, statistics, and logged timesheet hours."
            )
            return final_report
            
        except Exception as e:
            logger.error(f"Error in execute_pending_actions: {str(e)}")
            return f"❌ **Execution Failed:** An error occurred while executing the batch updates: {str(e)}"

orchestrator_agent = OrchestratorAgent()
