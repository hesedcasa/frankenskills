"""LLM-as-judge and simulated-user helpers, both run through `claude -p` with no tools."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile

from . import UsageLimitError, check_limit

JUDGE_SYSTEM = (
    "You are a strict, careful evaluator. Judge only from the material given. "
    "Reply with a single JSON object and nothing else."
)


def _call(prompt: str, model: str | None, system: str, timeout_s: int = 600) -> str:
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--max-turns", "1",
           "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands",
           "--system-prompt", system, "--tools", ""]
    if model:
        cmd += ["--model", model]
    with tempfile.TemporaryDirectory() as tmp:
        for attempt in range(3):
            proc = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True,
                                  timeout=timeout_s, stdin=subprocess.DEVNULL)
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError:
                data = None
            if data is not None and not data.get("is_error"):
                return data.get("result") or ""
            # An error must never be returned as text: it would be scored as a judgment
            # or handed to the agent as the simulated user's reply.
            check_limit((data or {}).get("result") or "")
            check_limit(proc.stderr)
            if attempt == 2:
                detail = (data or {}).get("result") or proc.stderr[-500:]
                raise RuntimeError(f"claude call failed: {detail}")
    return ""


def extract_json(text: str) -> dict:
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = [fence.group(1)] if fence else []
    start = text.find("{")
    if start != -1:
        candidates.append(text[start:text.rfind("}") + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"no JSON object in judge output: {text[:300]}")


def judge(prompt: str, model: str | None = None, retries: int = 2) -> dict:
    last = None
    for _ in range(retries + 1):
        try:
            return extract_json(_call(prompt, model, JUDGE_SYSTEM))
        except UsageLimitError:
            raise
        except (ValueError, RuntimeError) as e:
            last = e
    return {"_judge_error": str(last)}


SIM_USER_SYSTEM = """You are role-playing the person who asked a coding agent for help.
You know the full, true requirements (given below as HIDDEN SPEC). The agent saw only a
vaguer version. Rules:
- Answer only what the agent asked. Do not volunteer requirements it did not ask about.
- Answer from the HIDDEN SPEC. If a question is not covered by it, say you don't know or
  that the agent should use its judgment.
- Never paste the hidden spec, never write code, keep answers short and natural.
- If the agent asks you to approve something, approve it unless it contradicts the HIDDEN SPEC,
  in which case point out the contradiction briefly."""


def simulated_user_reply(hidden_spec: str, agent_message: str, model: str | None = None) -> str:
    prompt = (f"HIDDEN SPEC:\n<<<\n{hidden_spec}\n>>>\n\n"
              f"The agent just said:\n<<<\n{agent_message}\n>>>\n\nWrite your reply.")
    return _call(prompt, model, SIM_USER_SYSTEM).strip()


def classify_turn(agent_message: str, model: str | None = None) -> dict:
    """Is the agent waiting on the user (questions/approval) or did it just proceed?"""
    return judge(
        "Classify this message a coding agent sent to its user.\n\n"
        f"MESSAGE:\n<<<\n{agent_message[-6000:]}\n>>>\n\n"
        'Return JSON: {"asks_questions": bool, "questions": [string], '
        '"requests_approval": bool, "waiting_on_user": bool}. '
        "asks_questions is true only for questions about requirements or intent "
        "(not 'want me to continue?'). waiting_on_user is true if the agent stopped and "
        "needs a reply before it can proceed.",
        model,
    )
