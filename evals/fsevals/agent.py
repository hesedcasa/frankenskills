"""Run Claude Code headlessly in a sandbox workspace and capture what it did.

Arms (identical Claude Code setup, including its bundled skills; the only
difference is whether the five frankenskills are installed in the workspace):
  baseline        frankenskills not installed
  skill           all five frankenskills installed in the workspace, prompt
                  starts with /<skill> (measures the skill's content)
  skill-implicit  skills installed, plain prompt (measures whether the
                  description triggers the skill on its own)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import SKILL_NAMES, SKILLS_DIR, check_limit

ARMS = ("baseline", "skill", "skill-implicit")

ALLOWED_TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "Agent", "Task",
                 "TodoWrite", "Skill", "NotebookEdit"]
# No web access: several datasets are public and an agent could look up answers.
DISALLOWED_TOOLS = ["WebFetch", "WebSearch"]


@dataclass
class AgentResult:
    text: str = ""
    session_id: str = ""
    cost_usd: float = 0.0
    num_turns: int = 0
    duration_s: float = 0.0
    is_error: bool = False
    error: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    skills_invoked: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "tool_calls"} | {
            "n_tool_calls": len(self.tool_calls)
        }


def install_skills(workspace: Path) -> None:
    dest = workspace / ".claude" / "skills"
    dest.mkdir(parents=True, exist_ok=True)
    for name in SKILL_NAMES:
        shutil.copytree(SKILLS_DIR / name, dest / name, dirs_exist_ok=True)


def prompt_for_arm(arm: str, skill: str, task_prompt: str) -> str:
    return f"/{skill} {task_prompt}" if arm == "skill" else task_prompt


def run_agent(
    prompt: str,
    cwd: Path,
    arm: str,
    *,
    model: str | None = None,
    max_turns: int = 80,
    timeout_s: int = 1800,
    resume: str | None = None,
    transcript: Path | None = None,
    extra_env: dict | None = None,
) -> AgentResult:
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose",
        "--setting-sources", "project,local",
        "--strict-mcp-config",
        "--permission-mode", "acceptEdits",
        "--max-turns", str(max_turns),
        "--allowedTools", *ALLOWED_TOOLS,
        "--disallowedTools", *DISALLOWED_TOOLS,
    ]
    if model:
        cmd += ["--model", model]
    if resume:
        cmd += ["--resume", resume]
    env = os.environ | {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"} | (extra_env or {})

    res = AgentResult()
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout_s, env=env, stdin=subprocess.DEVNULL)
        out = proc.stdout
        if proc.returncode != 0 and not out.strip():
            res.is_error, res.error = True, proc.stderr[-2000:]
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        res.is_error, res.error = True, f"timeout after {timeout_s}s"
    res.duration_s = round(time.time() - t0, 1)

    if transcript:
        transcript.parent.mkdir(parents=True, exist_ok=True)
        with transcript.open("a") as f:
            f.write(out)

    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    call = {"name": block.get("name"), "input": block.get("input", {})}
                    res.tool_calls.append(call)
                    if call["name"] == "Skill":
                        res.skills_invoked.append(str(call["input"].get("skill", "")))
        elif ev.get("type") == "system" and ev.get("session_id"):
            res.session_id = res.session_id or ev["session_id"]
            if ev.get("subtype") == "init":
                # Slash-command expansions are not emitted in the stream, so credit a
                # leading /<skill> when that skill was actually loaded in this session.
                m = re.match(r"/([\w-]+)\s", prompt)
                if m and m.group(1) in (ev.get("skills") or []):
                    res.skills_invoked.append(m.group(1))
        elif ev.get("type") == "result":
            res.text = ev.get("result") or ""
            res.session_id = ev.get("session_id") or res.session_id
            res.cost_usd = float(ev.get("total_cost_usd") or 0)
            res.num_turns = int(ev.get("num_turns") or 0)
            if ev.get("is_error") or ev.get("subtype", "success") != "success":
                check_limit(res.text)
                res.is_error = True
                res.error = res.error or f"{ev.get('subtype')}: {res.text[:300]}"
    # Every loaded skill (slash command or Skill tool) injects its body with this marker.
    res.skills_invoked += re.findall(r"Base directory for this skill: \S*?/\.claude/skills/(\w[\w-]*)", out)
    res.skills_invoked = sorted(set(res.skills_invoked))
    return res


class Conversation:
    """A multi-turn session with one agent in one workspace."""

    def __init__(self, cwd: Path, arm: str, *, model=None, max_turns=80, timeout_s=1800,
                 transcript: Path | None = None, extra_env: dict | None = None):
        self.cwd, self.arm, self.model, self.extra_env = cwd, arm, model, extra_env
        self.max_turns, self.timeout_s, self.transcript = max_turns, timeout_s, transcript
        self.session_id: str | None = None
        self.turns: list[dict] = []
        self.cost_usd = 0.0
        self.tool_calls: list[dict] = []
        self.skills_invoked: set[str] = set()
        self.errors: list[str] = []

    def send(self, message: str) -> AgentResult:
        r = run_agent(message, self.cwd, self.arm, model=self.model, max_turns=self.max_turns,
                      timeout_s=self.timeout_s, resume=self.session_id,
                      transcript=self.transcript, extra_env=self.extra_env)
        self.session_id = r.session_id or self.session_id
        self.cost_usd += r.cost_usd
        self.tool_calls += r.tool_calls
        self.skills_invoked |= set(r.skills_invoked)
        if r.is_error:
            self.errors.append(r.error)
        self.turns.append({"user": message, "agent": r.text})
        return r

    def summary(self) -> dict:
        return {"cost_usd": round(self.cost_usd, 4), "agent_turns": len(self.turns),
                "n_tool_calls": len(self.tool_calls),
                "skills_invoked": sorted(self.skills_invoked), "errors": self.errors}
