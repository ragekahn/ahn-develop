"""Tests for ego_agent — ESM-script dispatch design (no network, subprocess mocked)."""
import json
from unittest import mock

import pytest

import ego_agent


def _fake_resp(tool_name, args, call_id="call_1"):
    """Build a minimal openai-style chat response containing one tool call."""
    tc = mock.Mock()
    tc.id = call_id
    tc.function.name = tool_name
    tc.function.arguments = json.dumps(args)
    msg = mock.Mock()
    msg.tool_calls = [tc]
    msg.content = ""
    choice = mock.Mock()
    choice.message = msg
    resp = mock.Mock()
    resp.choices = [choice]
    return resp


def _client_with_calls(responses):
    calls = iter(responses)
    fake = mock.Mock()
    fake.chat.completions.create.side_effect = lambda **_kw: next(calls)
    return fake


# ---- run_script --------------------------------------------------------

def test_run_script_writes_file_and_invokes_nodejs(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ego_agent, "SCRIPT_DIR", tmp_path)
    script = "console.log('hi');"
    fake_proc = mock.Mock(returncode=0, stdout="hi", stderr="")
    with mock.patch.object(ego_agent.subprocess, "run", return_value=fake_proc) as mrun:
        out = ego_agent.run_script(script, 1)

    mrun.assert_called_once()
    cmd = mrun.call_args.args[0]
    assert cmd[0] == str(ego_agent.EGO_BROWSER)
    assert cmd[1] == "nodejs"
    assert "-e" in cmd
    assert cmd[cmd.index("-e") + 1].startswith("await import('file://")

    written = list(tmp_path.glob("round-01.mjs"))
    assert len(written) == 1
    assert written[0].read_text(encoding="utf-8") == script
    assert "hi" in out


def test_run_script_merges_stderr(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ego_agent, "SCRIPT_DIR", tmp_path)
    fake_proc = mock.Mock(returncode=1, stdout="out", stderr="err")
    with mock.patch.object(ego_agent.subprocess, "run", return_value=fake_proc):
        out = ego_agent.run_script("x", 2)
    assert "out" in out and "err" in out


def test_run_script_timeout_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ego_agent, "SCRIPT_DIR", tmp_path)
    import subprocess as sp
    with mock.patch.object(ego_agent.subprocess, "run",
                           side_effect=sp.TimeoutExpired(cmd="ego", timeout=30)):
        out = ego_agent.run_script("x", 3)
    assert "timed out" in out.lower()


def test_run_script_missing_binary(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ego_agent, "SCRIPT_DIR", tmp_path)
    monkeypatch.setattr(ego_agent, "EGO_BROWSER", ego_agent.Path("definitely/not/here/ego-browser"))
    out = ego_agent.run_script("x", 4)
    assert "not found" in out


# ---- run_task dispatch -------------------------------------------------

def test_dispatch_ego_script_then_done(monkeypatch, capsys):
    monkeypatch.setattr(ego_agent, "client", _client_with_calls([
        _fake_resp("ego_script", {"script": "x = 1;"}),
        _fake_resp("task_done", {"summary": "all good"}),
    ]))
    with mock.patch.object(ego_agent, "run_script", return_value="EXECUTED:x = 1;") as mrun:
        ego_agent.run_task("do the thing")

    out = capsys.readouterr().out
    mrun.assert_called_once_with("x = 1;", 1)
    assert "COMPLETE: all good" in out


def test_dispatch_task_done_only(monkeypatch, capsys):
    monkeypatch.setattr(ego_agent, "client", _client_with_calls([
        _fake_resp("task_done", {"summary": "nothing to do"}),
    ]))
    with mock.patch.object(ego_agent, "run_script") as mrun:
        ego_agent.run_task("noop")

    assert not mrun.called
    assert "nothing to do" in capsys.readouterr().out


def test_dispatch_unknown_tool_reports_error(monkeypatch):
    monkeypatch.setattr(ego_agent, "client", _client_with_calls([
        _fake_resp("bogus_tool", {}),
        _fake_resp("task_done", {"summary": "done"}),
    ]))
    with mock.patch.object(ego_agent, "run_script") as mrun:
        ego_agent.run_task("x")

    assert not mrun.called


def test_tools_registry_exposes_both_schemas():
    names = [t["function"]["name"] for t in ego_agent.TOOLS]
    assert names == ["ego_script", "task_done"]
