import json

def get_summary_prompt(summary_data: dict, new_user_msg: str, new_agent_msg: str) -> str:
    return f"""You are an expert conversation analyzer.
Your task is to update the running summary of an ongoing chat between a User and an AI Assistant, and extract lists of projects mentioned, tasks mentioned, and actions taken.

Current Summary State:
{json.dumps(summary_data, indent=2)}

New messages to incorporate:
User: {new_user_msg}
Assistant: {new_agent_msg}

Analyze the new messages and integrate them into the existing state.
- Keep the summary concise but informative (max 3 sentences).
- Extract any projects mentioned.
- Extract any tasks mentioned.
- Extract any actions taken.
- Keep the existing lists and add new items (do not delete old items, but avoid duplicates).

Respond ONLY with a valid JSON object matching the format below. Do not include markdown code block formatting (like ```json), explanations, or trailing characters.

JSON Format:
{{
  "summary": "updated summary text...",
  "projects_mentioned": ["project1", "project2"],
  "tasks_mentioned": ["task1", "task2"],
  "actions_taken": ["action1", "action2"]
}}
"""

def get_main_agent_system_prompt(summary: str, stm_context_str: str, ltm_context_str: str, user_info: dict = None) -> str:
    user_header = ""
    if user_info:
        name = user_info.get("name")
        email = user_info.get("email")
        if name or email:
            user_header = f"\nYou are currently chatting with User: {name or 'N/A'} (Email: {email or 'N/A'}). Please address them by their name when appropriate.\n"

    return f"""You are a helpful, professional AI Chat Agent.{user_header}
You are interacting with the user in real-time.

Current Running Conversation Summary:
{summary}

[Historical Memory - Relevant Past Sessions]
{ltm_context_str}

[Current Session Context - Relevant Recent Messages]
{stm_context_str}

Please answer the user's message using the historical memory, current session context, and running summary to maintain continuity.
"""
