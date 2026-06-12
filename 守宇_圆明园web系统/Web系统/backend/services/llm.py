"""
LLM Provider 抽象层 —— 支持 OpenAI 兼容协议（DeepSeek等）与 Anthropic 原生协议。

提供统一的 stream_chat(messages, system) → AsyncIterator[dict] 接口。
"""
from typing import AsyncIterator
from ..settings import (
    LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_MAX_TOKENS,
)


def is_available() -> bool:
    """检查 LLM 是否可用。"""
    return bool(LLM_API_KEY)


async def stream_chat(
    messages: list[dict],
    system: str = "",
    model: str = "",
    max_tokens: int = 0,
) -> AsyncIterator[dict]:
    """
    流式调用 LLM API，逐 token yield。
    自动根据 LLM_PROVIDER 选择 OpenAI 兼容或 Anthropic 协议。
    """
    if not LLM_API_KEY:
        yield {"type": "error", "message": "LLM API Key 未配置。请设置环境变量 LLM_API_KEY。"}
        return

    if LLM_PROVIDER == "anthropic":
        async for event in _stream_anthropic(messages, system, model, max_tokens):
            yield event
    else:
        async for event in _stream_openai(messages, system, model, max_tokens):
            yield event


async def _stream_openai(
    messages: list[dict],
    system: str = "",
    model: str = "",
    max_tokens: int = 0,
) -> AsyncIterator[dict]:
    """OpenAI 兼容协议流式（DeepSeek / OpenAI / 国产模型通用）。"""
    import json
    import httpx

    model = model or LLM_MODEL
    max_tokens = max_tokens or LLM_MAX_TOKENS

    # 构建消息
    msg_list = []
    if system:
        msg_list.append({"role": "system", "content": system})
    for m in messages:
        msg_list.append({"role": m.get("role", "user"), "content": m.get("content", "")})

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    body = {
        "model": model,
        "messages": msg_list,
        "max_tokens": max_tokens,
        "stream": True,
        "temperature": 0.3,
        "thinking": {"type": "disabled"},
    }

    base = LLM_BASE_URL.rstrip("/")
    url = f"{base}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code != 200:
                    error_text = ""
                    async for chunk in response.aiter_text():
                        error_text += chunk
                    try:
                        err = json.loads(error_text)
                        msg = err.get("error", {}).get("message", "") or str(err)
                    except Exception:
                        msg = error_text[:200] or f"HTTP {response.status_code}"
                    yield {"type": "error", "message": f"LLM 错误：{msg}"}
                    return

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield {"type": "token", "text": content}
                    except json.JSONDecodeError:
                        continue

        # done
        yield {
            "type": "done",
            "usage": {"inputTokens": 0, "outputTokens": 0},
            "finishReason": "stop",
        }

    except httpx.TimeoutException:
        yield {"type": "error", "message": "LLM 请求超时，请重试。"}
    except Exception as e:
        yield {"type": "error", "message": f"LLM 调用错误：{str(e)}"}


async def _stream_anthropic(
    messages: list[dict],
    system: str = "",
    model: str = "",
    max_tokens: int = 0,
) -> AsyncIterator[dict]:
    """Claude API 原生流式。"""
    model = model or LLM_MODEL
    max_tokens = max_tokens or LLM_MAX_TOKENS

    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=LLM_API_KEY)

        msg_list = []
        for m in messages:
            msg_list.append({"role": m.get("role", "user"), "content": m.get("content", "")})

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": msg_list,
        }
        if system:
            kwargs["system"] = system

        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield {"type": "token", "text": text}

        final = await stream.get_final_message()
        usage = {
            "inputTokens": final.usage.input_tokens if final.usage else 0,
            "outputTokens": final.usage.output_tokens if final.usage else 0,
        }
        yield {
            "type": "done",
            "usage": usage,
            "finishReason": final.stop_reason or "stop",
        }

    except ImportError:
        yield {"type": "error", "message": "anthropic 库未安装。请运行 pip install anthropic。"}
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "unauthorized" in error_msg.lower():
            yield {"type": "error", "message": "LLM API Key 无效或未授权。"}
        elif "429" in error_msg or "rate" in error_msg.lower():
            yield {"type": "error", "message": "LLM 请求过于频繁，请稍后重试。"}
        elif "timeout" in error_msg.lower():
            yield {"type": "error", "message": "LLM 请求超时，请重试。"}
        else:
            yield {"type": "error", "message": f"LLM 调用错误：{error_msg}"}


async def chat_simple(
    prompt: str,
    system: str = "",
    model: str = "",
    max_tokens: int = 0,
) -> str:
    """非流式调用，用于实体抽取等轻任务。"""
    import json
    import httpx

    if not LLM_API_KEY:
        return ""

    model = model or LLM_MODEL
    max_tokens = max_tokens or min(LLM_MAX_TOKENS, 512)

    msg_list = []
    if system:
        msg_list.append({"role": "system", "content": system})
    msg_list.append({"role": "user", "content": prompt})

    base = LLM_BASE_URL.rstrip("/")
    url = f"{base}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": msg_list,
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                    "thinking": {"type": "disabled"},
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            return ""
    except Exception:
        return ""
