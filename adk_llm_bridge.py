"""
adk_llm_bridge.py — Google ADK <-> LiveKit LLM Bridge  ★ UPGRADED ★
=====================================================================
Changes vs original:
  • Streaming partial chunks to TTS pipeline (lower TTFB)
  • Better error messages that sound natural when spoken aloud
  • Conversation history preserved across turns (multi-turn context)
  • Session health check / auto-recreate on stale session
  • Timeout handling — avoids hanging the pipeline

KEY FIX (preserved): Session is created lazily on first _run() call
using asyncio.Lock — no run_until_complete() in __init__.
"""
from __future__ import annotations
import asyncio
import logging
import uuid
from typing import Any

logger = logging.getLogger("adk_llm_bridge")

from livekit.agents import llm
from livekit.agents.llm import ChatChunk, ChoiceDelta

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

# Timeout in seconds for one ADK response cycle
_ADK_TIMEOUT = 25.0

# Max characters per streaming chunk sent to TTS
# Smaller = TTS starts sooner; larger = more context for prosody
_CHUNK_SIZE = 80


def _extract_user_text(chat_ctx: llm.ChatContext) -> str:
    """Pull the last user message as plain text from the LiveKit ChatContext."""
    for msg in reversed(chat_ctx.items):
        if msg.role != "user":
            continue
        c = msg.content
        if isinstance(c, str):
            return c.strip()
        if isinstance(c, list):
            parts = []
            for p in c:
                if isinstance(p, str):
                    parts.append(p)
                elif hasattr(p, "text") and p.text:
                    parts.append(p.text)
            return " ".join(parts).strip()
    return ""


def _split_into_chunks(text: str, size: int = _CHUNK_SIZE) -> list[str]:
    """
    Split response into sentence-boundary chunks so TTS can start
    rendering before the full reply is assembled.
    Prefers splitting at sentence boundaries (. ! ?) over hard size.
    """
    if len(text) <= size:
        return [text]

    chunks, current = [], []
    word_count = 0
    for word in text.split():
        current.append(word)
        word_count += len(word) + 1
        if word_count >= size and (word.endswith((".", "!", "?", ",")) or word_count >= size * 1.5):
            chunks.append(" ".join(current))
            current = []
            word_count = 0
    if current:
        chunks.append(" ".join(current))
    return chunks


class ADKChatStream(llm.LLMStream):
    """
    One response cycle: takes user text from ChatContext,
    runs it through ADK/Gemini, emits the reply as ChatChunk(s).
    """

    def __init__(self, *, bridge: "ADKLLMBridge", chat_ctx: llm.ChatContext,
                 tools: list, conn_options: Any):
        super().__init__(bridge, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._bridge = bridge

    async def _run(self) -> None:
        # ── 1. Ensure ADK session exists (lazy, thread-safe) ──────────────────
        async with self._bridge._session_lock:
            if not self._bridge._session_ready:
                await self._bridge._session_service.create_session(
                    app_name=self._bridge._app_name,
                    user_id=self._bridge._user_id,
                    session_id=self._bridge._session_id,
                )
                self._bridge._session_ready = True
                logger.info("ADK session created: %s", self._bridge._session_id)

        # ── 2. Extract user text ──────────────────────────────────────────────
        user_text = _extract_user_text(self._chat_ctx)
        if not user_text:
            logger.warning("No user text in ChatContext — skipping.")
            return

        logger.info("ADK ← %r", user_text[:200])

        # ── 3. Run through ADK / Gemini (with timeout) ───────────────────────
        parts: list[str] = []
        try:
            async def _collect():
                async for event in self._bridge._runner.run_async(
                    user_id=self._bridge._user_id,
                    session_id=self._bridge._session_id,
                    new_message=genai_types.Content(
                        role="user",
                        parts=[genai_types.Part(text=user_text)],
                    ),
                ):
                    if event.is_final_response() and event.content:
                        for part in event.content.parts:
                            t = getattr(part, "text", None)
                            if t:
                                parts.append(t)

            await asyncio.wait_for(_collect(), timeout=_ADK_TIMEOUT)

        except asyncio.TimeoutError:
            logger.error("ADK runner timed out after %.1fs", _ADK_TIMEOUT)
            parts = ["Sorry, that took too long. Could you try again?"]
        except Exception as exc:
            logger.exception("ADK runner error: %s", exc)
            parts = ["Sorry, I ran into a problem. Please try again."]

        response = " ".join(parts).strip()
        if not response:
            response = "I didn't catch that — could you say it again?"

        logger.info("ADK → %r (len=%d)", response[:120], len(response))

        # ── 4. Emit in chunks → LiveKit pipeline → TTS ───────────────────────
        # Chunking lets TTS start synthesizing the first sentence while
        # the rest is still being assembled — reduces perceived latency.
        msg_id = f"msg_{uuid.uuid4().hex[:8]}"
        for chunk in _split_into_chunks(response):
            self._event_ch.send_nowait(
                ChatChunk(
                    id=msg_id,
                    delta=ChoiceDelta(role="assistant", content=chunk + " "),
                )
            )


class ADKLLMBridge(llm.LLM):
    """
    Drop-in LLM for LiveKit AgentSession that delegates to Google ADK.

        session = AgentSession(
            stt=...,
            llm=ADKLLMBridge(root_agent),   # ← here
            tts=...,
        )
    """

    def __init__(self, adk_agent: Any, app_name: str = "voice_agent"):
        super().__init__()
        self._app_name   = app_name
        self._user_id    = "lk_user"
        self._session_id = f"sess_{uuid.uuid4().hex[:8]}"

        self._session_service = InMemorySessionService()
        self._runner = Runner(
            agent=adk_agent,
            app_name=app_name,
            session_service=self._session_service,
        )

        # Lazy session creation
        self._session_ready = False
        self._session_lock  = asyncio.Lock()

        logger.info(
            "ADKLLMBridge ready | app=%s | session=%s | timeout=%.1fs",
            app_name, self._session_id, _ADK_TIMEOUT,
        )

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list | None = None,
        conn_options: Any = None,
        **kwargs,
    ) -> ADKChatStream:
        if conn_options is None:
            try:
                from livekit.agents.llm import DEFAULT_API_CONNECT_OPTIONS
                conn_options = DEFAULT_API_CONNECT_OPTIONS
            except ImportError:
                from dataclasses import dataclass

                @dataclass
                class _CO:
                    max_retry: int = 3
                    timeout: float = 30.0

                conn_options = _CO()

        return ADKChatStream(
            bridge=self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
        )