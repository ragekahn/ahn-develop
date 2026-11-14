#!/usr/bin/env python3
"""
ego_agent.py — Local AI browser automation agent (Ollama + ego-browser)

ego-browser v0.6+ runs JavaScript via an embedded Node.js runtime.
The LLM generates a small ESM script each step; we write it to a .mjs file
and invoke it with:

    ego-browser nodejs -e "await import('file:///.../round-NN.mjs')"

No API subscription required — qwen3.8:27b runs locally on Ollama.

Usage:
    python ego_agent.py                          # interactive REPL
    python ego_agent.py "go to example.com"      # one-shot
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────
EGO_BROWSER = r"C:\Users\ezury\.local\share\ego\active_version_dir\ego-browser"
OLLAMA_URL  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
MODEL       = os.getenv("OLLAMA_MODEL",     "qwen3.8:27b")
MAX_STEPS   = int(os.getenv("EGO_MAX_STEPS", "25"))
EGO_TIMEOUT = int(os.getenv("EGO_CMD_TIMEOUT", "120"))
SCRIPT_DIR  = Path(os.getenv("EGO_AGENT_DIR", r"C:\Users\ezury\ego-agent"))
SCRIPT_DIR.mkdir(parents=True, exist_ok=True)

from openai import OpenAI
client = OpenAI(base_url=OLLAMA_URL, api_key="ollama")

# ── System prompt ───────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are ego-agent, a local browser-automation agent. You drive the ego-browser
Node.js runtime through the ego_script tool. Each call executes a self-contained
ESM JavaScript script in a fresh Node process.

## Bootstrap (write these two lines at the top of every ego_script)

    const task = await taskSpace("ego-agent");
    const page = task.page("p1");

Write the bootstrap plus your *actions*. `taskSpace()` is a global; `task.page("p1")` is the default page of a fresh space.

## Available page APIs (ego-browser custom — NOT Playwright)

    await page.goto(url)                       Navigate
    const snap = await page.snapshot()         Structured snapshot w/ @refs
    await page.click(selector)                 @ref | text=... | loc=css:... | #id
    await page.fill(selector, text)            type into input
    await page.selectOption(sel, {label})      or {value: "..."}
    await page.press(selector, key)            "Enter","Tab","Escape",...
    await page.evaluate(jsExpr)                Run browser-side JS, returns value
    await page.screenshot({path})              Returns absolute file path
    await page.mouse.click(x, y)               Coordinate click (canvas etc.)
    await page.keyboard.paste(text)            Native clipboard paste

## Selector formats

  @21                 ref from the last snapshot (preferred)
  text=Save           visible text substring, case-insensitive
  text="Save"         exact text match
  loc=css:#btn        CSS
  loc=role:button[name='Save']
  #btn, .cls          raw CSS also works
  xpath=//button[@id='x']

## Rules

1. Navigate first:  await page.goto("https://...");  then snapshot.
2. After navigation or page changes, call page.snapshot() and console.log it
   before deciding what to click.
3. Prefer @refs from the snapshot. If the page changed, take a new snapshot
   and use the new refs.
4. Print useful output with console.log(...) so the caller can read it.
5. When the goal is fully achieved, call the task_done tool with a concise
   summary. Do NOT call task_done until you have the final answer.
6. Respond with tool calls only — no free text outside tool arguments.
7. If a selector fails, snapshot again and try a different selector.
"""


def run_script(script: str, round_no: int) -> str:
    """Save the JS script to ego-agent/round-NN.mjs and run it via ego-browser nodejs.

    The script is a complete ESM program (it calls taskSpace() itself). Its
    stdout/stderr are returned so the model can read the results and plan the
    next round.
    """
    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    script_path = SCRIPT_DIR / f"round-{round_no:02d}.mjs"
    script_path.write_text(script, encoding="utf-8")

    # e.g. file:///C:/Users/ezury/ego-agent/round-01.mjs
    url = script_path.as_uri()
    code = f"await import('{url}')"
    cmd = [EGO_BROWSER, "nodejs", "-e", code]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=EGO_TIMEOUT)
        parts = []
        if r.stdout:
            parts.append(r.stdout)
        if r.stderr:
            parts.append(f"[stderr] {r.stderr}")
        if r.returncode != 0:
            parts.append(f"[exit {r.returncode}]")
        return "\n".join(parts) if parts else "[no output]"
    except subprocess.TimeoutExpired:
        return f"[ERROR] Timed out after {EGO_TIMEOUT}s"
    except FileNotFoundError:
        return f"[ERROR] ego-browser not found: {EGO_BROWSER}"
    except Exception as exc:
        return f"[ERROR] {exc}"


EGO_SCRIPT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ego_script",
        "description": (
            "Run one round of browser automation. Pass a complete JavaScript (ESM) "
            "script that uses the pre-existing global taskSpace(). It is saved to "
            "ego-agent/round-NN.mjs and executed with 'ego-browser nodejs'. Its "
            "console.log output is returned to you as the next context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": (
                        "Full ESM script body. Start with the bootstrap "
                        "(const task = await taskSpace(\"ego-agent\"); "
                        "const page = task.page(\"p1\")); then the actions."
                    ),
                },
            },
            "required": ["script"],
        },
    },
}

TASK_DONE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "task_done",
        "description": "Finish the task and report a concise, human-readable result.",
        "parameters": {
            "type": "object",
            "properties": {
                "result": {
                    "type": "string",
                    "description": "The final answer / summary for the user.",
                },
            },
            "required": ["result"],
        },
    },
}

TOOLS = [EGO_SCRIPT_SCHEMA, TASK_DONE_SCHEMA]


def run_task(user_prompt: str) -> None:
    """Execute one user task through the LLM → ego-browser loop."""
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    for step in range(1, MAX_STEPS + 1):
        print(f"  step {step}/{MAX_STEPS} …", flush=True)

        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.1,
            max_tokens=1024,
        )

        msg = resp.choices[0].message
        asst: dict = {"role": "assistant"}
        if msg.content:
            asst["content"] = msg.content
            print(f"  💬 {msg.content[:200]}")

        tool_calls = msg.tool_calls or []
        if not tool_calls:
            print(f"  ✅ Done: {(msg.content or '').strip()}")
            return

        asst["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in tool_calls
        ]
        messages.append(asst)

        task_done = False
        for tc in tool_calls:
            name = tc.function.name
            try:
                parsed = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
            except (json.JSONDecodeError, TypeError):
                parsed = {}

            if name == "task_done":
                summary = (parsed.get("summary", "") or "").strip()
                print(f"  ✅ COMPLETE: {summary or 'Task finished.'}")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": summary or "Task finished."})
                task_done = True
                break

            if name == "ego_script":
                script = parsed.get("script", "")
                if not script:
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": "[ERROR] ego_script called with empty script."})
                    continue
                print(f"  ⚡ ego-browser nodejs  round-{step:02d}.mjs …", flush=True)
                output = run_script(script, step)
                print(f"  📄 {output[:300]}{'…' if len(output) > 300 else ''}")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": output})
            else:
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": f"[ERROR] Unknown tool: {name}"})

        if task_done:
            break
    else:
        print(f"  ⚠️  Reached max steps ({MAX_STEPS}) — task may be incomplete.")


def main() -> None:
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        print(f"\n🌐 ego-agent | model={MODEL} | task: {prompt}\n")
        run_task(prompt)
        return

    print(f"""
  🌐 ego-agent  —  local AI browser automation
     model   : {MODEL}
     ollama  : {OLLAMA_URL}
     browser : ego-browser

     Type a task and press Enter.
     Examples:
       "go to https://news.ycombinator.com and list the top 3 headlines"
       "open google.com, search for 'weather in Seoul', take a screenshot"
     Type `quit` to exit.
""")
    while True:
        try:
            user_input = input("  you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Bye!")
            break
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("  Bye!")
            break

        print(f"\n  🚀 task: {user_input}\n")
        run_task(user_input)
        print()


if __name__ == "__main__":
    main()


