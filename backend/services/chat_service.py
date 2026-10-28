"""Gemini streaming chat orchestration with simple, explicit tool handling."""

import json
import logging
import os
import time
from collections.abc import Iterator
from typing import Any

from google import genai
from google.genai import types

from prompts.system_prompt import SYSTEM_PROMPT
from tools.email_tool import send_email
from tools.ticket_tool import raise_ticket

log = logging.getLogger("timing")

TOOL_DEFINITIONS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="raise_ticket",
                description="Create a local support ticket for a complaint, issue, refund/cancellation concern or human escalation.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "summary": types.Schema(type="STRING"),
                        "category": types.Schema(
                            type="STRING",
                            enum=["complaint", "technical", "payment", "enrollment", "refund", "cancellation", "human_escalation", "other"],
                        ),
                    },
                    required=["summary", "category"],
                ),
            ),
            types.FunctionDeclaration(
                name="send_email",
                description="Send an enrollment confirmation, callback request or escalation using the configured email app.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "subject": types.Schema(type="STRING"),
                        "body": types.Schema(type="STRING", description="you must Include contact details of the user mandatory= (name, phone, email). Politely request user if you dint receive any information"),
                    },
                    required=["subject", "body"],
                ),
            ),
        ]
    )
]


def _client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    return genai.Client(api_key=api_key)


def _config(allow_tools: bool) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=TOOL_DEFINITIONS,
        tool_config=None if allow_tools else types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="NONE")),
        thinking_config=types.ThinkingConfig(thinking_level=os.getenv("GEMINI_THINKING_LEVEL", "low")),
        temperature=0.2,
    )


def _safe_messages(messages: list[dict[str, Any]]) -> list[types.Content]:
    """Keep the last 16 user/assistant messages, converted to Gemini's user/model roles."""
    safe: list[types.Content] = []
    for message in messages[-16:]:
        role, content = message.get("role"), message.get("content", "")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            safe.append(
                types.Content(
                    role="user" if role == "user" else "model",
                    parts=[types.Part.from_text(text=content.strip()[:6000])],
                )
            )
    return safe


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _execute_tool(name: str, arguments: dict[str, Any], latest_user_text: str) -> dict[str, Any]:
    if name == "raise_ticket":
        return raise_ticket(arguments.get("summary", latest_user_text), arguments.get("category", "other"), latest_user_text)
    if name == "send_email":
        to_address = os.getenv("EMAIL_TO")
        if not to_address:
            return {"ok": False, "error": "EMAIL_TO is not configured in backend/.env."}
        return send_email(to_address, arguments["subject"], arguments["body"])
    return {"ok": False, "error": f"Unknown tool: {name}"}


def stream_assistant_reply(messages: list[dict[str, Any]]) -> Iterator[str]:
    """Yield Server-Sent Events: status, token, action, done, or error.

    Round 1 streams with tools enabled: plain answers reach the user immediately.
    If the model calls a tool, we run it and do round 2 (tools off) for the final reply.
    """
    try:
        client = _client()
        model = os.getenv("GEMINI_CHAT_MODEL")
        contents = _safe_messages(messages)
        latest_user_text = next((m.parts[0].text for m in reversed(contents) if m.role == "user"), "")
        yield _sse("status", {"message": "Thinking..."})

        full_reply = ""
        for round_no in (1, 2):
            start = time.perf_counter()
            first = True
            model_parts: list[Any] = []
            calls: list[Any] = []

            for chunk in client.models.generate_content_stream(model=model, contents=contents, config=_config(allow_tools=round_no == 1)):
                if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                    model_parts.extend(chunk.candidates[0].content.parts)
                calls.extend(chunk.function_calls or [])
                token = chunk.text or ""
                if token:
                    if first:
                        log.info("llm round %d first token: %.0f ms", round_no, (time.perf_counter() - start) * 1000)
                        first = False
                    full_reply += token
                    yield _sse("token", {"content": token})
            log.info("llm round %d total: %.0f ms (tool calls: %d)", round_no, (time.perf_counter() - start) * 1000, len(calls))

            if not calls:
                break

            # Keep the model's own parts as-is (preserves any thought signatures).
            contents.append(types.Content(role="model", parts=model_parts))
            response_parts = []
            for call in calls:
                tool_start = time.perf_counter()
                result = _execute_tool(call.name, dict(call.args or {}), latest_user_text)
                log.info("tool %s: %.0f ms", call.name, (time.perf_counter() - tool_start) * 1000)
                yield _sse("action", {"name": call.name, "result": result})
                response_parts.append(types.Part.from_function_response(name=call.name, response=result))
            contents.append(types.Content(role="user", parts=response_parts))

        yield _sse("done", {"text": full_reply})
    except Exception as error:
        yield _sse("error", {"message": str(error)})