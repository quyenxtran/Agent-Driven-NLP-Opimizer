from __future__ import annotations

import hashlib
import json
import re
import textwrap
import time
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from urllib import error, request


def utc_now_text() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def required_keys_missing(data: Optional[Dict[str, object]], required_keys: Sequence[str]) -> List[str]:
    if not isinstance(data, dict):
        return list(required_keys)
    return [key for key in required_keys if key not in data]


class OpenAICompatClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        enabled: bool,
        api_key: str = "ollama",
        fallback_enabled: bool = False,
        fallback_base_url: str = "",
        fallback_model: str = "",
        fallback_api_key: str = "",
        conversation_stream_path: Optional[Path] = None,
        timeout_seconds: float = 300.0,
        max_tokens: int = 320,
        max_retries: int = 2,
        retry_backoff_seconds: float = 2.0,
        conversation_log_mode: str = "compact",
        conversation_response_max_chars: int = 1200,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.enabled = enabled and bool(self.base_url) and bool(self.model)
        self.fallback_base_url = fallback_base_url.rstrip("/")
        self.fallback_model = fallback_model
        self.fallback_api_key = fallback_api_key
        self.fallback_enabled = (
            fallback_enabled
            and bool(self.fallback_base_url)
            and bool(self.fallback_model)
            and bool(self.fallback_api_key)
        )
        self.last_backend = "none"
        self.call_counter = 0
        self.conversations: List[Dict[str, object]] = []
        self.conversation_stream_path = conversation_stream_path
        self.timeout_seconds = max(5.0, float(timeout_seconds))
        self.max_tokens = max(32, int(max_tokens))
        self.max_retries = max(1, int(max_retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self.conversation_log_mode = str(conversation_log_mode or "compact").strip().lower()
        if self.conversation_log_mode not in {"compact", "full"}:
            self.conversation_log_mode = "compact"
        self.conversation_response_max_chars = max(120, int(conversation_response_max_chars))

    @staticmethod
    def _sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

    def _record_for_storage(self, record: Dict[str, object]) -> Dict[str, object]:
        if self.conversation_log_mode == "full":
            return record
        messages = record.get("messages") if isinstance(record.get("messages"), list) else []
        system_text = ""
        user_text = ""
        if len(messages) >= 1 and isinstance(messages[0], dict):
            system_text = str(messages[0].get("content", ""))
        if len(messages) >= 2 and isinstance(messages[1], dict):
            user_text = str(messages[1].get("content", ""))
        assistant_text = str(record.get("assistant_response", "")) if "assistant_response" in record else ""
        compact: Dict[str, object] = {
            "call_id": record.get("call_id"),
            "timestamp_utc": record.get("timestamp_utc"),
            "role": record.get("role"),
            "metadata": record.get("metadata", {}),
            "attempts": record.get("attempts", []),
            "final_backend": record.get("final_backend"),
            "prompt_stats": {
                "system_chars": len(system_text),
                "user_chars": len(user_text),
                "system_sha256": self._sha256(system_text),
                "user_sha256": self._sha256(user_text),
                "user_preview": user_text[:220],
            },
        }
        if assistant_text:
            compact["assistant_response_preview"] = assistant_text[: self.conversation_response_max_chars]
            compact["assistant_response_chars"] = len(assistant_text)
        return compact

    def _append_conversation_stream(self, record: Dict[str, object]) -> None:
        if self.conversation_stream_path is None:
            return
        try:
            self.conversation_stream_path.parent.mkdir(parents=True, exist_ok=True)
            with self.conversation_stream_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        except Exception:
            # Streaming is best-effort; full transcript is still persisted at run end.
            return

    def _chat_once(
        self,
        base_url: str,
        model: str,
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        stop_sequences: Sequence[str],
        require_json_output: bool,
    ) -> Tuple[Optional[str], str]:
        if not base_url or not model:
            return None, "missing_base_url_or_model"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        def build_payload(
            include_stop: bool,
            include_temperature: bool,
            include_max_tokens: bool,
            include_json_mode: bool,
        ) -> Dict[str, object]:
            payload: Dict[str, object] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            if include_temperature:
                payload["temperature"] = temperature
            if include_stop:
                payload["stop"] = list(stop_sequences)
            if include_max_tokens:
                payload["max_tokens"] = self.max_tokens
            if include_json_mode:
                payload["response_format"] = {"type": "json_object"}
            return payload

        # Some providers/models reject stop sequences, custom temperature controls,
        # or max_tokens naming. Try progressively simpler payloads.
        payload_variants: List[Tuple[str, Dict[str, object]]] = []
        base_shapes = [
            ("full", True, True, True),
            ("no_stop", False, True, True),
            ("no_temp", True, False, True),
            ("no_stop_no_temp", False, False, True),
            ("no_stop_no_temp_no_max", False, False, False),
        ]
        if require_json_output:
            for name, include_stop, include_temperature, include_max_tokens in base_shapes:
                payload_variants.append(
                    (f"json_{name}", build_payload(include_stop, include_temperature, include_max_tokens, True))
                )
        for name, include_stop, include_temperature, include_max_tokens in base_shapes:
            payload_variants.append(
                (name, build_payload(include_stop, include_temperature, include_max_tokens, False))
            )
        last_error = "unknown_error"

        for variant_name, payload in payload_variants:
            for attempt in range(1, self.max_retries + 1):
                req = request.Request(
                    f"{base_url}/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                try:
                    with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                    return body["choices"][0]["message"]["content"], ""
                except error.HTTPError as exc:
                    response_body = ""
                    try:
                        response_body = exc.read().decode("utf-8", errors="replace")
                    except Exception:
                        response_body = ""
                    response_body = " ".join(response_body.split())[:320]
                    last_error = f"http_error_{exc.code}" + (f": {response_body}" if response_body else "")

                    # Retry transient HTTP failures.
                    if exc.code in {408, 429, 500, 502, 503, 504} and attempt < self.max_retries:
                        if self.retry_backoff_seconds > 0:
                            time.sleep(self.retry_backoff_seconds * attempt)
                        continue

                    # If the provider rejects stop controls, retry with the next payload variant
                    # that omits stop. This must apply to any variant that currently includes stop.
                    if (
                        exc.code == 400
                        and "stop" in payload
                        and "stop" in response_body.lower()
                        and ("unsupported" in response_body.lower() or "not supported" in response_body.lower())
                    ):
                        break
                    # If the provider rejects custom temperature values, retry with the next payload
                    # variant that omits temperature.
                    if (
                        exc.code == 400
                        and "temperature" in payload
                        and "temperature" in response_body.lower()
                        and ("unsupported" in response_body.lower() or "default" in response_body.lower())
                    ):
                        break
                    # If provider rejects max_tokens naming, retry a variant without it.
                    if (
                        exc.code == 400
                        and "max_tokens" in payload
                        and "max_tokens" in response_body.lower()
                        and ("unsupported" in response_body.lower() or "not supported" in response_body.lower())
                    ):
                        break
                    # If provider rejects response_format JSON mode, retry without it.
                    if (
                        exc.code == 400
                        and "response_format" in payload
                        and (
                            "response_format" in response_body.lower()
                            or "json_object" in response_body.lower()
                            or "json mode" in response_body.lower()
                        )
                    ):
                        break
                    return None, last_error
                except error.URLError as exc:
                    last_error = f"url_error_{str(exc.reason)}"
                    if attempt < self.max_retries:
                        if self.retry_backoff_seconds > 0:
                            time.sleep(self.retry_backoff_seconds * attempt)
                        continue
                    return None, last_error
                except TimeoutError:
                    last_error = "timeout"
                    if attempt < self.max_retries:
                        if self.retry_backoff_seconds > 0:
                            time.sleep(self.retry_backoff_seconds * attempt)
                        continue
                    return None, last_error
                except KeyError:
                    return None, "missing_choices_message_content"
                except json.JSONDecodeError:
                    return None, "invalid_json_response"
                except Exception as exc:  # pragma: no cover - defensive fallback
                    return None, f"unexpected_error_{type(exc).__name__}"
        return None, last_error

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_role: str = "generic",
        metadata: Optional[Dict[str, object]] = None,
        temperature: float = 0.2,
        stop_sequences: Optional[Sequence[str]] = None,
        require_json_output: bool = False,
    ) -> Optional[str]:
        resolved_stop = tuple(stop_sequences or ("<|endoftext|>", "<|im_start|>", "<|im_end|>"))
        self.call_counter += 1
        record: Dict[str, object] = {
            "call_id": self.call_counter,
            "timestamp_utc": utc_now_text(),
            "role": conversation_role,
            "metadata": metadata or {},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "attempts": [],
        }

        if self.enabled:
            content, err = self._chat_once(
                self.base_url,
                self.model,
                self.api_key,
                system_prompt,
                user_prompt,
                temperature,
                resolved_stop,
                require_json_output,
            )
            record["attempts"].append(
                {
                    "backend": "primary",
                    "base_url": self.base_url,
                    "model": self.model,
                    "success": content is not None,
                    "error": err,
                }
            )
            if content is not None:
                self.last_backend = "primary"
                record["final_backend"] = self.last_backend
                record["assistant_response"] = content
                stored_record = self._record_for_storage(record)
                self.conversations.append(stored_record)
                self._append_conversation_stream(stored_record)
                return content
        if self.fallback_enabled:
            content, err = self._chat_once(
                self.fallback_base_url,
                self.fallback_model,
                self.fallback_api_key,
                system_prompt,
                user_prompt,
                temperature,
                resolved_stop,
                require_json_output,
            )
            record["attempts"].append(
                {
                    "backend": "fallback",
                    "base_url": self.fallback_base_url,
                    "model": self.fallback_model,
                    "success": content is not None,
                    "error": err,
                }
            )
            if content is not None:
                self.last_backend = "fallback"
                record["final_backend"] = self.last_backend
                record["assistant_response"] = content
                stored_record = self._record_for_storage(record)
                self.conversations.append(stored_record)
                self._append_conversation_stream(stored_record)
                return content
        self.last_backend = "none"
        record["final_backend"] = self.last_backend
        stored_record = self._record_for_storage(record)
        self.conversations.append(stored_record)
        self._append_conversation_stream(stored_record)
        return None

    @staticmethod
    def extract_json(text: Optional[str]) -> Optional[Dict[str, object]]:
        if not text:
            return None
        cleaned = text
        # Keep chain-of-thought enabled upstream, but strip think blocks before JSON decoding.
        cleaned = re.sub(
            r"<\s*think\s*>.*?<\s*/\s*think\s*>",
            "",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )
        for marker in ("<|endoftext|>", "<|im_start|>", "<|im_end|>"):
            idx = cleaned.find(marker)
            if idx != -1:
                cleaned = cleaned[:idx]
        decoder = json.JSONDecoder()
        for match in re.finditer(r"{", cleaned):
            start = match.start()
            try:
                candidate, _ = decoder.raw_decode(cleaned[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                return candidate
        return None


def request_json_with_single_repair(
    client: OpenAICompatClient,
    *,
    system_prompt: str,
    user_prompt: str,
    conversation_role: str,
    metadata: Dict[str, object],
    temperature: float,
    required_keys: Sequence[str],
) -> Tuple[Optional[Dict[str, object]], Optional[str], bool, str]:
    raw = client.chat(
        system_prompt,
        user_prompt,
        conversation_role=conversation_role,
        metadata=metadata,
        temperature=temperature,
        require_json_output=True,
    )
    data = client.extract_json(raw)
    missing = required_keys_missing(data, required_keys)
    if isinstance(data, dict) and not missing:
        return data, raw, False, ""

    repair_reason = "missing required keys" if missing else "invalid JSON response"
    placeholder: Dict[str, object] = {}
    for k in required_keys:
        if "index" in k:
            placeholder[k] = 0
        elif any(x in k for x in ("refs", "evidence", "comparison", "alternatives", "rationale")):
            placeholder[k] = ["<your text here>"]
        else:
            placeholder[k] = "<your text here>"
    example_json = json.dumps(placeholder, separators=(",", ":"))
    repair_prompt = textwrap.dedent(
        f"""
        Your previous response was invalid for role={conversation_role}.
        Failure reason: {repair_reason}.
        Required keys: {list(required_keys)}.

        Example of the required JSON structure (replace placeholder values with real content):
        {example_json}

        Return ONLY a valid JSON object with all required keys filled in.
        Do not include markdown, analysis text, or any text outside the JSON object.

        Previous response:
        {str(raw or '')[:1400]}
        """
    ).strip()
    repair_raw = client.chat(
        system_prompt,
        repair_prompt,
        conversation_role=f"{conversation_role}_repair",
        metadata={**metadata, "repair_reason": repair_reason},
        temperature=0.0,
        require_json_output=True,
    )
    repair_data = client.extract_json(repair_raw)
    repair_missing = required_keys_missing(repair_data, required_keys)
    if isinstance(repair_data, dict) and not repair_missing:
        return repair_data, repair_raw, True, ""
    return None, repair_raw, True, repair_reason
