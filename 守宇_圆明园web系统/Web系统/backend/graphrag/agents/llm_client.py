"""这个文件封装与大模型交互的底层客户端和 JSON 解析逻辑。"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional

from ..logging_utils import log_event

try:
    from json_repair import repair_json as _repair_json
except Exception:
    _repair_json = None


DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_THINKING = os.environ.get("DEEPSEEK_THINKING", "disabled").strip().lower() or "disabled"
DEEPSEEK_REASONING_EFFORT = os.environ.get("DEEPSEEK_REASONING_EFFORT", "").strip().lower()


def _strip_code_fences(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.S | re.I)
    if fenced:
        return fenced.group(1).strip()
    return text


def _extract_balanced_json(text: str) -> str:
    text = _strip_code_fences(text)
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return ""


def extract_json_object(text: str) -> Dict[str, Any]:
    text = _strip_code_fences(text)
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    candidate = _extract_balanced_json(text)
    if candidate:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    if _repair_json:
        try:
            repaired = _repair_json(text)
            if repaired:
                data = json.loads(repaired)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def _response_preview(body: Dict[str, Any]) -> str:
    try:
        return json.dumps(body, ensure_ascii=False)[:1200]
    except Exception:
        return str(body)[:1200]


def _call_chat_once(
    messages: List[Dict[str, str]],
    api_key: str,
    json_mode: bool = True,
    max_tokens: int = 1200,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    payload["thinking"] = {"type": "enabled" if DEEPSEEK_THINKING == "enabled" else "disabled"}
    if DEEPSEEK_THINKING == "enabled" and DEEPSEEK_REASONING_EFFORT in {"high", "max"}:
        payload["reasoning_effort"] = DEEPSEEK_REASONING_EFFORT
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        f"{DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    choice = (body.get("choices") or [{}])[0] or {}
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        fragments: List[str] = []
        for item in content:
            if isinstance(item, dict):
                text_part = item.get("text") or item.get("content") or ""
                if text_part:
                    fragments.append(str(text_part))
            elif item:
                fragments.append(str(item))
        content = "".join(fragments)
    return {
        "content": content or "",
        "finish_reason": choice.get("finish_reason", ""),
        "usage": body.get("usage", {}),
        "body_preview": _response_preview(body),
        "message_preview": _response_preview(message),
        "model": body.get("model", DEEPSEEK_MODEL),
        "thinking": DEEPSEEK_THINKING,
    }


def _build_retry_prompt(prompt: str, json_mode: bool) -> str:
    if json_mode:
        return (
            f"{prompt}\n\n"
            "Return exactly one valid JSON object. Do not wrap it in markdown fences. "
            "Do not add explanations before or after the JSON."
        )
    return (
        f"{prompt}\n\n"
        "Return a complete textual answer directly. Do not leave the answer blank."
    )


def call_chat(messages: List[Dict[str, str]], api_key: str, json_mode: bool = True, max_tokens: int = 1200) -> str:
    result = _call_chat_once(messages, api_key, json_mode=json_mode, max_tokens=max_tokens)
    return result["content"]


def _call_with_retry(
    messages: List[Dict[str, str]],
    api_key: str,
    run_id: str,
    stage: str,
    json_mode: bool,
    max_tokens: int,
) -> Dict[str, Any]:
    last_result: Optional[Dict[str, Any]] = None
    for attempt in range(1, 3):
        current_messages = messages
        if attempt == 2:
            retry_messages = [dict(m) for m in messages]
            retry_messages[-1]["content"] = _build_retry_prompt(retry_messages[-1]["content"], json_mode=json_mode)
            current_messages = retry_messages
        result = _call_chat_once(current_messages, api_key, json_mode=json_mode, max_tokens=max_tokens)
        last_result = result
        log_event(
            run_id,
            f"{stage}.response",
            {
                "attempt": attempt,
                "model": result.get("model", DEEPSEEK_MODEL),
                "thinking": result.get("thinking", DEEPSEEK_THINKING),
                "finish_reason": result.get("finish_reason", ""),
                "usage": result.get("usage", {}),
                "content_preview": (result.get("content") or "")[:1200],
                "message_preview": result.get("message_preview", ""),
            },
        )
        content = (result.get("content") or "").strip()
        if content:
            return result
        log_event(
            run_id,
            f"{stage}.empty_response",
            {
                "attempt": attempt,
                "model": result.get("model", DEEPSEEK_MODEL),
                "thinking": result.get("thinking", DEEPSEEK_THINKING),
                "finish_reason": result.get("finish_reason", ""),
                "body_preview": result.get("body_preview", ""),
            },
        )
    return last_result or {"content": "", "finish_reason": "", "usage": {}, "body_preview": "", "message_preview": ""}


def call_json_agent(
    prompt: str,
    api_key: str,
    run_id: str,
    stage: str,
    system_prompt: str,
    max_tokens: int = 1200,
) -> Dict[str, Any]:
    log_event(run_id, f"{stage}.request", {"prompt_preview": prompt[:1200]})
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        result = _call_with_retry(
            messages,
            api_key,
            run_id=run_id,
            stage=stage,
            json_mode=True,
            max_tokens=max_tokens,
        )
        content = result.get("content", "")
        parsed = extract_json_object(content)
        if parsed:
            return parsed
        log_event(
            run_id,
            f"{stage}.invalid_json",
            {
                "content_preview": content[:1200],
                "finish_reason": result.get("finish_reason", ""),
                "body_preview": result.get("body_preview", ""),
            },
        )
        if content.strip():
            retry_messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": _build_retry_prompt(prompt, json_mode=True),
                },
            ]
            retry_result = _call_chat_once(retry_messages, api_key, json_mode=False, max_tokens=max_tokens)
            log_event(
                run_id,
                f"{stage}.repair_response",
                {
                    "finish_reason": retry_result.get("finish_reason", ""),
                    "usage": retry_result.get("usage", {}),
                    "content_preview": (retry_result.get("content") or "")[:1200],
                    "message_preview": retry_result.get("message_preview", ""),
                },
            )
            repaired = extract_json_object(retry_result.get("content", ""))
            if repaired:
                return repaired
            log_event(
                run_id,
                f"{stage}.repair_invalid_json",
                {
                    "body_preview": retry_result.get("body_preview", ""),
                },
            )
        return {}
    except Exception as exc:
        log_event(run_id, f"{stage}.error", {"error": str(exc)})
        return {}


def call_text_agent(
    prompt: str,
    api_key: str,
    run_id: str,
    stage: str,
    system_prompt: str,
    max_tokens: int = 1200,
) -> str:
    log_event(run_id, f"{stage}.request", {"prompt_preview": prompt[:1200]})
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        result = _call_with_retry(
            messages,
            api_key,
            run_id=run_id,
            stage=stage,
            json_mode=False,
            max_tokens=max_tokens,
        )
        content = (result.get("content") or "").strip()
        return content
    except Exception as exc:
        log_event(run_id, f"{stage}.error", {"error": str(exc)})
        return ""
