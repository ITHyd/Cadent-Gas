from __future__ import annotations

from typing import Any, Dict

import httpx

from .config import settings


class MistralClient:
    @property
    def enabled(self) -> bool:
        return bool(settings.mistral_api_key)

    async def parse_intent(self, user_text: str) -> Dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("Mistral is not configured")

        system_prompt = (
            "You are an intent parser for a Slack bot. "
            "Map user requests into one of these commands only: "
            "help, incident, company-stats, pending-incidents, agent-jobs, "
            "my-incidents, available-agents, kb-stats, kb-true, kb-false, kb-recent. "
            "Return strict JSON only with keys: matched, command, args, confidence, reason. "
            "Rules: "
            "1. If no supported command matches, set matched=false. "
            "2. Keep args as a simple array of strings in execution order. "
            "3. Extract incident ids like INC-1001 exactly. "
            "4. Extract agent ids like agent_001 and user ids like user_001 exactly. "
            "5. company-stats, pending-incidents, kb-stats, kb-true, kb-false, kb-recent take no args by default. "
            "6. available-agents takes no args. "
            "7. Allow minor spelling mistakes and paraphrases. "
            "8. Never invent ids that are missing from user input. "
            "9. If the user asks for unsupported write actions, set matched=false."
        )

        payload = {
            "model": settings.mistral_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(
            base_url=settings.mistral_base_url,
            timeout=settings.request_timeout_seconds,
        ) as client:
            response = await client.post(
                "/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.mistral_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))

        import json
        return json.loads(content)


mistral_client = MistralClient()
