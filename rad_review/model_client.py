from __future__ import annotations

import base64
import json
import mimetypes
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class ModelConfig:
    base_url: str
    api_key: str
    text_model: str
    vision_base_url: str
    vision_api_key: str
    vision_model: str
    wire_api: str = "chat_completions"
    vision_wire_api: str = "chat_completions"
    seed: int | None = None

    @classmethod
    def from_env(cls) -> "ModelConfig":
        seed_value = os.getenv("AI_SEED", "").strip()
        return cls(
            base_url=os.getenv("AI_BASE_URL", "").strip(),
            api_key=os.getenv("AI_API_KEY", "").strip(),
            text_model=os.getenv("AI_MODEL", "").strip(),
            vision_base_url=os.getenv("AI_VISION_BASE_URL", "").strip(),
            vision_api_key=os.getenv("AI_VISION_API_KEY", "").strip(),
            vision_model=os.getenv("AI_VISION_MODEL", "").strip(),
            wire_api=os.getenv("AI_WIRE_API", "chat_completions").strip().lower() or "chat_completions",
            vision_wire_api=os.getenv("AI_VISION_WIRE_API", "chat_completions").strip().lower() or "chat_completions",
            seed=parse_seed(seed_value),
        )

    @classmethod
    def from_prefixed_env(cls, prefix: str) -> "ModelConfig":
        prefix = prefix.strip().upper()
        if not prefix:
            raise RuntimeError("ModelConfig.from_prefixed_env requires a non-empty prefix.")

        seed_value = os.getenv(f"{prefix}_SEED", "").strip() or os.getenv("AI_SEED", "").strip()
        return cls(
            base_url=os.getenv(f"{prefix}_BASE_URL", "").strip(),
            api_key=os.getenv(f"{prefix}_API_KEY", "").strip(),
            text_model=os.getenv(f"{prefix}_MODEL", "").strip(),
            vision_base_url=os.getenv("AI_VISION_BASE_URL", "").strip(),
            vision_api_key=os.getenv("AI_VISION_API_KEY", "").strip(),
            vision_model=os.getenv("AI_VISION_MODEL", "").strip(),
            wire_api=os.getenv(f"{prefix}_WIRE_API", "chat_completions").strip().lower() or "chat_completions",
            vision_wire_api=os.getenv("AI_VISION_WIRE_API", "chat_completions").strip().lower() or "chat_completions",
            seed=parse_seed(seed_value),
        )

    @property
    def has_text_model(self) -> bool:
        return bool(self.base_url and self.api_key and self.text_model)

    @property
    def has_vision_model(self) -> bool:
        return bool(self.vision_base_url_or_default and self.vision_api_key_or_default and self.vision_model)

    @property
    def vision_base_url_or_default(self) -> str:
        return self.vision_base_url or self.base_url

    @property
    def vision_api_key_or_default(self) -> str:
        return self.vision_api_key or self.api_key

    def missing_text_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.base_url:
            missing.append("AI_BASE_URL")
        if not self.api_key:
            missing.append("AI_API_KEY")
        if not self.text_model:
            missing.append("AI_MODEL")
        return missing

    def missing_vision_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.vision_base_url_or_default:
            missing.append("AI_VISION_BASE_URL/AI_BASE_URL")
        if not self.vision_api_key_or_default:
            missing.append("AI_VISION_API_KEY/AI_API_KEY")
        if not self.vision_model:
            missing.append("AI_VISION_MODEL")
        return missing


def parse_seed(value: str) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError("AI_SEED must be an integer when set.") from exc


class OpenAICompatibleClient:
    def __init__(
        self,
        config: ModelConfig,
        timeout: int = 600,
        event_logger: Callable[..., None] | None = None,
    ) -> None:
        self.config = config
        self.timeout = timeout
        self.event_logger = event_logger

    def set_event_logger(self, event_logger: Callable[..., None] | None) -> None:
        self.event_logger = event_logger

    def chat(self, messages: list[dict[str, Any]], model: str | None = None, temperature: float = 0) -> str:
        selected_model = model or self.config.text_model
        if not self.config.base_url or not self.config.api_key or not selected_model:
            raise RuntimeError("Missing AI_BASE_URL, AI_API_KEY, or model name.")
        return self._chat_with_wire_api(
            selected_model,
            messages,
            temperature=temperature,
            wire_api=self.config.wire_api,
            wire_api_label="AI_WIRE_API",
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            seed=self.config.seed,
        )

    def analyze_image(self, image_path: Path, prompt: str) -> str:
        self._validate_vision_model_hint()
        mime = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
        data = base64.b64encode(image_path.read_bytes()).decode("ascii")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}},
                ],
            }
        ]
        analysis = self._chat_with_wire_api(
            self.config.vision_model,
            messages,
            temperature=None,
            wire_api=self.config.vision_wire_api,
            wire_api_label="AI_VISION_WIRE_API",
            base_url=self.config.vision_base_url_or_default,
            api_key=self.config.vision_api_key_or_default,
        )
        if self._looks_like_missing_image_response(analysis):
            raise RuntimeError(
                "Vision model responded as if no image was provided. "
                "Check AI_VISION_MODEL / AI_VISION_WIRE_API compatibility."
        )
        return analysis

    def _validate_vision_model_hint(self) -> None:
        model = (self.config.vision_model or "").strip().lower()
        if model.startswith("deepseek-v4"):
            raise RuntimeError(
                "AI_VISION_MODEL is set to a DeepSeek V4 text model. "
                "DeepSeek's documented Chat Completions schema is text-only and does not document image input for deepseek-v4-pro/flash. "
                "Use a real vision/OCR backend instead."
            )

    def _chat_with_wire_api(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float | None,
        wire_api: str,
        wire_api_label: str,
        base_url: str,
        api_key: str,
        seed: int | None = None,
    ) -> str:
        if wire_api == "responses":
            response = self._post_responses(
                self._responses_payload(model, messages, temperature, seed=seed),
                base_url=base_url,
                api_key=api_key,
            )
            return self._extract_responses_text(response)
        if wire_api in ("claude", "claude_messages", "anthropic", "anthropic_messages"):
            response = self._post_anthropic_messages(
                self._anthropic_messages_payload(model, messages, temperature),
                base_url=base_url,
                api_key=api_key,
            )
            return self._extract_anthropic_text(response)
        if wire_api not in ("chat_completions", "chat-completions", "chat"):
            raise RuntimeError(f"Unsupported {wire_api_label}: {wire_api}")
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if seed is not None:
            payload["seed"] = seed
        response = self._post_chat(payload, base_url=base_url, api_key=api_key)
        return self._extract_chat_text(response)

    def _post_chat(self, payload: dict[str, Any], base_url: str, api_key: str) -> dict[str, Any]:
        url = base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            if not url.endswith("/v1"):
                url = f"{url}/v1"
            url = f"{url}/chat/completions"

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                self._log_event("model http response received", endpoint="chat_completions")
                return payload
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Model API HTTP {exc.code}: {detail}") from exc
        except TimeoutError as exc:
            raise RuntimeError(
                f"Model API request timed out after {self.timeout}s. "
                f"Try increasing --timeout or lowering --max-context-chars."
            ) from exc
        except socket.timeout as exc:
            raise RuntimeError(
                f"Model API request timed out after {self.timeout}s. "
                f"Try increasing --timeout or lowering --max-context-chars."
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Model API request failed: {exc}") from exc

    def _post_responses(self, payload: dict[str, Any], base_url: str, api_key: str) -> dict[str, Any]:
        url = base_url.rstrip("/")
        if not url.endswith("/responses"):
            if not url.endswith("/v1"):
                url = f"{url}/v1"
            url = f"{url}/responses"
        return self._post_json(url, payload, api_key=api_key)

    def _post_anthropic_messages(self, payload: dict[str, Any], base_url: str, api_key: str) -> dict[str, Any]:
        url = base_url.rstrip("/")
        if not url.endswith("/messages"):
            if not url.endswith("/v1"):
                url = f"{url}/v1"
            url = f"{url}/messages"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                self._log_event("model http response received", endpoint="anthropic_messages")
                return payload
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Model API HTTP {exc.code}: {detail}") from exc
        except TimeoutError as exc:
            raise RuntimeError(
                f"Model API request timed out after {self.timeout}s. "
                f"Try increasing --timeout or lowering --max-context-chars."
            ) from exc
        except socket.timeout as exc:
            raise RuntimeError(
                f"Model API request timed out after {self.timeout}s. "
                f"Try increasing --timeout or lowering --max-context-chars."
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Model API request failed: {exc}") from exc

    def _post_json(self, url: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                endpoint = url.rsplit("/", 1)[-1]
                self._log_event("model http response received", endpoint=endpoint)
                return payload
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Model API HTTP {exc.code}: {detail}") from exc
        except TimeoutError as exc:
            raise RuntimeError(
                f"Model API request timed out after {self.timeout}s. "
                f"Try increasing --timeout or lowering --max-context-chars."
            ) from exc
        except socket.timeout as exc:
            raise RuntimeError(
                f"Model API request timed out after {self.timeout}s. "
                f"Try increasing --timeout or lowering --max-context-chars."
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Model API request failed: {exc}") from exc

    def _responses_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float | None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        instructions: list[str] = []
        input_messages: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system":
                instructions.append(str(content))
                continue
            input_messages.append(
                {
                    "role": role if role in ("user", "assistant") else "user",
                    "content": self._responses_content(content),
                }
            )
        payload: dict[str, Any] = {
            "model": model,
            "input": input_messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if seed is not None:
            payload["seed"] = seed
        if instructions:
            payload["instructions"] = "\n\n".join(instructions)
        return payload

    def _anthropic_messages_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float | None,
    ) -> dict[str, Any]:
        system_parts: list[str] = []
        converted_messages: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system":
                system_parts.append(str(content))
                continue
            converted_messages.append(
                {
                    "role": role if role in ("user", "assistant") else "user",
                    "content": self._anthropic_content(content),
                }
            )
        payload: dict[str, Any] = {
            "model": model,
            "messages": converted_messages,
            "max_tokens": 8192,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        return payload

    def _anthropic_content(self, content: Any) -> list[dict[str, Any]]:
        if isinstance(content, str):
            return [{"type": "text", "text": content}]
        converted: list[dict[str, Any]] = []
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    converted.append({"type": "text", "text": str(item)})
                    continue
                item_type = item.get("type")
                if item_type == "text":
                    converted.append({"type": "text", "text": item.get("text", "")})
                    continue
                if item_type == "image_url":
                    image_url = item.get("image_url", {})
                    image_ref = image_url.get("url", image_url)
                    if isinstance(image_ref, str) and image_ref.startswith("data:"):
                        header, data = image_ref.split(",", 1)
                        media_type = header[5:].split(";", 1)[0] or "application/octet-stream"
                        converted.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": data,
                                },
                            }
                        )
                        continue
                converted.append({"type": "text", "text": json.dumps(item, ensure_ascii=False)})
            return converted
        return [{"type": "text", "text": str(content)}]

    def _responses_content(self, content: Any) -> Any:
        if isinstance(content, str):
            return [{"type": "input_text", "text": content}]
        converted: list[dict[str, Any]] = []
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    converted.append({"type": "input_text", "text": str(item)})
                    continue
                item_type = item.get("type")
                if item_type == "text":
                    converted.append({"type": "input_text", "text": item.get("text", "")})
                elif item_type == "image_url":
                    image_url = item.get("image_url", {})
                    converted.append({"type": "input_image", "image_url": image_url.get("url", image_url)})
                else:
                    converted.append(item)
            return converted
        return [{"type": "input_text", "text": str(content)}]

    def _extract_chat_text(self, response: dict[str, Any]) -> str:
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected chat-completions response shape: {response}") from exc
        if isinstance(content, str):
            self._log_event("model text extracted", wire_api="chat_completions", chars=len(content))
            return content
        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        texts.append(text)
            if texts:
                joined = "\n".join(texts)
                self._log_event("model text extracted", wire_api="chat_completions", chars=len(joined))
                return joined
        raise RuntimeError(f"Unexpected chat-completions message content: {content}")

    def _extract_responses_text(self, response: dict[str, Any]) -> str:
        if isinstance(response.get("output_text"), str):
            text = response["output_text"]
            self._log_event("model text extracted", wire_api="responses", chars=len(text))
            return text
        texts: list[str] = []
        for output in response.get("output", []) or []:
            for content in output.get("content", []) or []:
                if isinstance(content, dict):
                    if isinstance(content.get("text"), str):
                        texts.append(content["text"])
                    elif isinstance(content.get("content"), str):
                        texts.append(content["content"])
        if texts:
            joined = "\n".join(texts)
            self._log_event("model text extracted", wire_api="responses", chars=len(joined))
            return joined
        raise RuntimeError(f"Unexpected responses API response shape: {response}")

    def _extract_anthropic_text(self, response: dict[str, Any]) -> str:
        texts: list[str] = []
        for content in response.get("content", []) or []:
            if isinstance(content, dict) and content.get("type") == "text" and isinstance(content.get("text"), str):
                texts.append(content["text"])
        if texts:
            joined = "\n".join(texts)
            self._log_event("model text extracted", wire_api="claude", chars=len(joined))
            return joined
        raise RuntimeError(f"Unexpected anthropic messages response shape: {response}")

    def _log_event(self, message: str, **fields: Any) -> None:
        if self.event_logger is not None:
            self.event_logger(message, **fields)

    def _looks_like_missing_image_response(self, text: str) -> bool:
        lowered = text.lower()
        patterns = (
            "未上传图片",
            "没有看到您上传的图片",
            "没有看到你提到的",
            "没有看到图片",
            "看不到你提到的",
            "看不到您提到的",
            "无法看到文档内容",
            "无法访问您提供的图片内容",
            "未检测到您上传的",
            "图片缺失",
            "当前对话未附带任何文档截图或图片文件",
            "please upload",
            "image was provided",
            "no image was provided",
            "i can't see the image",
            "i cannot see the image",
        )
        return any(pattern in lowered for pattern in patterns)
