import json
import logging
import asyncio
from src.Config.model import llm
from src.Config.redis import get_redis, set_value, delete_value, get_value
from langchain_core.messages import SystemMessage, HumanMessage

# Import Tools
from src.tools.query.list_projects import ListProjectsTool
from src.tools.query.list_tasks import ListTasksTool
from src.tools.action.create_task import CreateTaskTool
from src.tools.action.update_task import UpdateTaskTool
from src.tools.action.delete_task import DeleteTaskTool
from src.tools.action.create_project import CreateProjectTool
from src.tools.action.update_project import UpdateProjectTool
from src.tools.action.delete_project import DeleteProjectTool

# Import Prompts
from src.agnets.prompt import ORCHESTRATOR_PLANNING_PROMPT

logger = logging.getLogger("agent-service")

async def extract_project_id(query: str, context_str: str) -> str | None:
    prompt = f"""You are a Zoho Project ID Extractor. Your job is to extract the 18-digit Zoho Project ID from the context or the user query.
    
    Context and Query:
    {context_str}
    User Query: {query}
    
    If a project name is mentioned and has an ID like "mew mew (ID: 457314000000069061)", return exactly the 18-digit number (e.g. 457314000000069061).
    If no project ID is found, but a project name is found, search the query and context. If nothing is found, return "null".
    Do not include any explanation or extra text. Return ONLY the 18-digit project ID or "null"."""
    
    try:
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content="Please extract the Zoho Project ID according to the system instructions.")
        ]
        resp = await llm.ainvoke(messages)
        val = resp.content.strip()
        return val if val != "null" and val.isdigit() else None
    except Exception as e:
        logger.error(f"Error in extract_project_id: {str(e)}")
        return None

async def select_project_from_list(query: str, projects: list) -> str | None:
    prompt = f"""Select the correct project ID from the list below that matches the user's query: "{query}".
    Projects:
    {json.dumps(projects, indent=2)}
    
    Return ONLY the 18-digit project ID of the matching project. If no project matches, return "null"."""
    try:
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content="Please select the matching Zoho Project ID according to the system instructions.")
        ]
        resp = await llm.ainvoke(messages)
        val = resp.content.strip()
        return val if val != "null" and val.isdigit() else None
    except Exception as e:
        logger.error(f"Error in select_project_from_list: {str(e)}")
        return None

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
        else:
            return {"action": action, "args": args, "result": {"success": False, "error": "Unknown action type"}}
    except Exception as e:
        return {"action": action, "args": args, "result": {"success": False, "error": str(e)}}


class OrchestratorAgent:
    """
    OrchestratorAgent coordinates multi-step retrieval, filtering, and bulk operations.
    Handles querying project tasks, logical LLM-driven filtering, multi-action caching,
    and concurrent execution upon confirmation.
    """
    async def initiate_orchestration(
        self,
        query: str,
        session_id: str,
        access_token: str,
        stm_context: list[str] = None,
        summary: str = None
    ) -> str:
        # Format current context
        from src.utils.date_utils import get_current_date_context
        context_str = get_current_date_context() + "\n\n"
        if summary:
            context_str += f"[Conversation entity details / Active project context]:\n{summary}\n\n"
        if stm_context:
            context_str += "[Recent Chat History context]:\n"
            context_str += "\n".join(stm_context) + "\n\n"

        # Step 1: Resolve Project ID
        project_id = await extract_project_id(query, context_str)
        if not project_id:
            # Fallback search all projects
            projects_tool = ListProjectsTool(access_token)
            projects_result = await projects_tool.run()
            if projects_result.get("success") and projects_result.get("projects"):
                projects = projects_result["projects"]
                if len(projects) == 1:
                    project_id = projects[0]["id"]
                else:
                    project_id = await select_project_from_list(query, projects)
                    
        if not project_id:
            return "⚠️ I couldn't identify which project you are referring to. Could you please specify the project name or ID?"

        # Step 2: Fetch Tasks list for the resolved project
        tasks_tool = ListTasksTool(access_token)
        tasks_result = await tasks_tool.run(project_id)
        if not tasks_result.get("success") or "tasks" not in tasks_result:
            err = tasks_result.get("error", "Unknown Zoho Projects error")
            return f"❌ Failed to fetch task list for project verification: {err}"
            
        tasks = tasks_result["tasks"]
        if not tasks:
            return "📁 The selected project has no active tasks to analyze."

        # Step 3: Run the Planner LLM to build the update list
        messages = [
            SystemMessage(content=ORCHESTRATOR_PLANNING_PROMPT),
            HumanMessage(content=f"User Query: {query}\nProject ID: {project_id}\nRetrieved Tasks List:\n{json.dumps(tasks, indent=2)}")
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
            
            plan = json.loads(resp_text)
        except Exception as parse_err:
            logger.error(f"Failed to parse Orchestrator routing JSON: {resp_text}. Error: {str(parse_err)}")
            return "I encountered an error preparing the multi-task update plan. Could you please clarify your request?"

        if plan.get("clarification_needed"):
            return plan["clarification_needed"]
            
        actions = plan.get("actions", [])
        if not actions:
            return "🔍 Scanning complete: I couldn't find any uncompleted tasks matching your query to update."

        # Step 4: Cache proposed write actions in Redis as a batch
        redis = await get_redis()
        redis_key = f"pending_actions:{session_id}"
        
        cache_payload = {
            "project_id": project_id,
            "actions": actions
        }
        await set_value(redis, redis_key, json.dumps(cache_payload), 300) # 5 minutes TTL
        
        # Step 5: Render beautiful Confirmation Card with clickable links
        confirmation_details = []
        action_labels = {
            "create_project": "Create Project",
            "update_project": "Update Project",
            "delete_project": "Delete Project",
            "create_task": "Create Task",
            "update_task": "Update Task",
            "delete_task": "Delete Task"
        }
        
        for idx, act in enumerate(actions, 1):
            args = act["args"] or {}
            act_type = act["action"]
            label = action_labels.get(act_type, "Update")
            t_name = args.get("name") or "Task"
            t_id = args.get("task_id")
            
            # Create interactive deep link
            t_link = f"[{t_name}](task://{project_id}/{t_id})" if t_id else t_name
            
            mod_details = []
            for k, v in args.items():
                if k not in ("project_id", "task_id", "name") and v:
                    mod_details.append(f"  - **{k.replace('_', ' ').title()}**: `{v}`")
            
            mod_str = "\n".join(mod_details)
            confirmation_details.append(f"{idx}. **{label}**: {t_link}\n{mod_str}")
            
        args_formatted = "\n".join(confirmation_details)
        plan_desc = plan.get("plan_description", "Batch updates prepared.")

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
                t_id = args.get("task_id") or run_res.get("task_id")
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
                            updates.append(f"{k.replace('_', ' ')}: `{v}`")
                    update_str = ", ".join(updates) if updates else "Executed successfully"
                    report_lines.append(f"| {t_link} | ✅ Success | {update_str} |")
                else:
                    fail_count += 1
                    err_msg = run_res.get("error", "Zoho API error")
                    report_lines.append(f"| {t_link} | ❌ Failed | {err_msg} |")
            
            report_table = "\n".join(report_lines)
            
            final_report = f"""### ✅ Batch Execution Report

I have executed **{len(actions)}** write operations in parallel on Zoho Projects. Here is the summary:

*   **Successfully Updated**: {success_count} task(s)
*   **Failed**: {fail_count} task(s)

| Task Link | Execution Status | Updates Made / Error Message |
| --- | --- | --- |
{report_table}

***
You can click on any updated task name to open its interactive detail popup modal with comprehensive allocations, statistics, and logged timesheet hours.
"""
            return final_report
            
        except Exception as e:
            logger.error(f"Error in execute_pending_actions: {str(e)}")
            return f"❌ **Execution Failed:** An error occurred while executing the batch updates: {str(e)}"

orchestrator_agent = OrchestratorAgent()
