from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import AuthenticatedPrincipal
from app.services.ai_foundry_service import AIFoundryService
from app.services.ai_knowledge_base import render_knowledge_base
from app.services.ai_tools import AIToolbox, ToolExecutionResult

logger = logging.getLogger(__name__)


@dataclass
class AgentAnswer:
    answer: str
    sources: list[dict[str, Any]]
    grounded_context: dict[str, Any]
    suggested_followups: list[str]


class AIAgentService:
    MAX_TOOL_CALLS = 4
    MAX_TOOL_CONTEXT_CHARS = 16_000
    MAX_HISTORY_MESSAGES = 8

    def __init__(self) -> None:
        self.foundry_service = AIFoundryService()
        self.toolbox = AIToolbox()

    def is_enabled(self) -> bool:
        return self.foundry_service.chat_enabled

    def answer(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        user_message: str,
        history: list[dict[str, str]],
    ) -> AgentAnswer:
        if not self.is_enabled():
            raise RuntimeError("Azure AI chat is not configured")

        client = self.foundry_service.get_openai_client()
        messages = [{"role": "system", "content": self._system_prompt(principal)}]
        messages.extend(history[-self.MAX_HISTORY_MESSAGES :])
        messages.append({"role": "user", "content": user_message})

        tool_results: list[ToolExecutionResult] = []
        total_context_chars = 0

        while len(tool_results) < self.MAX_TOOL_CALLS:
            completion = client.chat.completions.create(
                model=self.foundry_service.settings.azure_ai_model_deployment,
                temperature=0.1,
                tools=self.toolbox.tool_definitions,
                tool_choice="auto",
                messages=messages,
            )
            assistant_message = completion.choices[0].message
            tool_calls = getattr(assistant_message, "tool_calls", None) or []
            if not tool_calls:
                if assistant_message.content:
                    messages.append({"role": "assistant", "content": assistant_message.content})
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                        for tool_call in tool_calls
                    ],
                }
            )

            for tool_call in tool_calls:
                if len(tool_results) >= self.MAX_TOOL_CALLS:
                    break
                args = self._parse_tool_args(tool_call.function.arguments)
                result = self.toolbox.execute(db, principal, tool_call.function.name, args)
                result_text = self.toolbox.result_to_message(result)
                total_context_chars += len(result_text)
                if total_context_chars > self.MAX_TOOL_CONTEXT_CHARS:
                    raise RuntimeError("AI tool context budget exceeded")
                tool_results.append(result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_text,
                    }
                )

        final_completion = client.chat.completions.create(
            model=self.foundry_service.settings.azure_ai_model_deployment,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=messages
            + [
                {
                    "role": "system",
                    "content": (
                        "Return strict JSON with keys: answer, sources, grounded_context, suggested_followups. "
                        "Use only data from the curated knowledge base, current conversation, and tool outputs. "
                        "sources must be an array of objects with label, type, and optional tool_name. "
                        "grounded_context must include used_tools, confidence, and optional time_range."
                    ),
                }
            ],
        )
        payload = self._parse_json_response(final_completion.choices[0].message.content or "{}")
        sanitized_sources = self._sanitize_sources(payload.get("sources"), tool_results)
        grounded_context = self._sanitize_grounded_context(payload.get("grounded_context"), tool_results)
        suggested_followups = [str(item).strip() for item in payload.get("suggested_followups", []) if str(item).strip()][:3]

        return AgentAnswer(
            answer=str(payload.get("answer") or "").strip(),
            sources=sanitized_sources,
            grounded_context=grounded_context,
            suggested_followups=suggested_followups,
        )

    def _system_prompt(self, principal: AuthenticatedPrincipal) -> str:
        return (
            "You are SpendPilot's finance operations assistant.\n"
            "Only answer using: (1) the curated knowledge base below, (2) the authenticated user's permitted tenant "
            "data returned by tools, and (3) the current conversation.\n"
            "Never invent numbers, hidden approvals, or unseen documents.\n"
            "Never claim that data was checked unless a tool returned it.\n"
            "For finance questions, prefer tool calls over guessing.\n"
            "For broad queries, use safe defaults like the current month or recent 30 days unless the user asks "
            "for a different time range.\n"
            "For document questions, prefer metadata or scan tools before requesting excerpts.\n"
            "Do not expose implementation details, raw SQL, secrets, internal credentials, or cross-tenant data.\n"
            f"Current user role: {principal.role}. Organization: {principal.organization_name}. Default currency: {principal.default_currency}.\n"
            "Curated knowledge base:\n"
            f"{render_knowledge_base()}"
        )

    @staticmethod
    def _parse_tool_args(raw_arguments: str) -> dict[str, Any]:
        if not raw_arguments:
            return {}
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="AI tool arguments were not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="AI tool arguments must be a JSON object")
        return parsed

    @staticmethod
    def _parse_json_response(raw_payload: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw_payload)
        except json.JSONDecodeError:
            logger.warning("AI agent returned non-JSON payload: %s", raw_payload)
            return {"answer": raw_payload.strip(), "sources": [], "grounded_context": {"confidence": "low"}, "suggested_followups": []}
        if not isinstance(parsed, dict):
            return {"answer": str(parsed), "sources": [], "grounded_context": {"confidence": "low"}, "suggested_followups": []}
        return parsed

    @staticmethod
    def _sanitize_sources(raw_sources: Any, tool_results: list[ToolExecutionResult]) -> list[dict[str, Any]]:
        valid_tool_names = {item.tool_name: item.source_label for item in tool_results}
        sanitized: list[dict[str, Any]] = []
        for item in raw_sources or []:
            if not isinstance(item, dict):
                continue
            source_type = str(item.get("type") or "tool")
            tool_name = str(item.get("tool_name") or "").strip() or None
            label = str(item.get("label") or "").strip()
            if tool_name and tool_name in valid_tool_names:
                sanitized.append({"label": label or valid_tool_names[tool_name], "type": source_type, "tool_name": tool_name})
            elif source_type == "knowledge_base":
                sanitized.append({"label": label or "Knowledge base", "type": "knowledge_base"})
        if not sanitized and tool_results:
            sanitized = [{"label": item.source_label, "type": "tool", "tool_name": item.tool_name} for item in tool_results]
        return sanitized[:6]

    @staticmethod
    def _sanitize_grounded_context(raw_context: Any, tool_results: list[ToolExecutionResult]) -> dict[str, Any]:
        context = raw_context if isinstance(raw_context, dict) else {}
        used_tools = [item.tool_name for item in tool_results]
        confidence = str(context.get("confidence") or ("high" if used_tools else "medium"))
        return {
            "used_tools": used_tools,
            "confidence": confidence if confidence in {"high", "medium", "low"} else "medium",
            "time_range": context.get("time_range"),
        }
