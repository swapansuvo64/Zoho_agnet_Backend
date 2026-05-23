import json
import logging
import httpx
from src.Config.settings import settings
from src.agnets.prompt import get_main_agent_system_prompt

logger = logging.getLogger("agent-service")

class MainAgent:
    async def get_response_stream(self, query: str, context: list[str], summary: str):
        context_str = "\n".join(f"- {c}" for c in context) if context else "No relevant context found."
        
        system_prompt = get_main_agent_system_prompt(summary, context_str)


        payload = {
            "model": settings.MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            "stream": True,
            "temperature": 0.7
        }

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }



        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("POST", url, json=payload, headers=headers, timeout=30.0) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        logger.error(f"Groq API returned error status {response.status_code}: {err_body.decode()}")
                        yield f"Error calling Groq API: {response.status_code}"
                        return
                        
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        line = line.strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                chunk = data["choices"][0]["delta"].get("content", "")
                                if chunk:
                                    yield chunk
                            except Exception:
                                continue
        except Exception as e:
            logger.error(f"Exception while streaming from Groq: {str(e)}")
            yield f"Error in LLM streaming client: {str(e)}"

main_agent = MainAgent()
