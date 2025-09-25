from __future__ import annotations
from app.services.langgraph.graph.consult.nodes.ask_missing import ask_missing_node
from app.services.langgraph.prompting import render_template

def test_rwdr_missing_prompt_contains_expected_labels():
    state = {"consult_required": True, "domain": "rwdr", "params": {}, "messages":[{"role":"user","content":"rwdr"}]}
    res = ask_missing_node(state)
    msg = res["messages"][0].content
    assert "Welle (mm)" in msg
    assert "Gehäuse (mm)" in msg
    assert "Breite (mm)" in msg
    assert "Druck (bar)" in msg
    assert res.get("ui_event", {}).get("form_id") == "rwdr_params_v1"
    assert res.get("phase") == "ask_missing"

def test_hyd_missing_prompt_contains_expected_labels():
    state = {"consult_required": True, "domain": "hydraulics_rod", "params": {}, "messages":[{"role":"user","content":"hyd"}]}
    res = ask_missing_node(state)
    msg = res["messages"][0].content
    assert "Stange (mm)" in msg
    assert "Nut-Ø D (mm)" in msg
    assert "Nutbreite B (mm)" in msg
    assert "Relativgeschwindigkeit (m/s)" in msg
    assert res.get("ui_event", {}).get("form_id") == "hydraulics_rod_params_v1"

def test_followups_template_renders_list():
    out = render_template("ask_missing_followups.jinja2",
                          followups=["Tmax plausibel bei v≈3 m/s?", "Druck > 200 bar bestätigt?"])
    assert "Bevor ich empfehle" in out
    assert "- Tmax plausibel bei v≈3 m/s?" in out
    assert "- Druck > 200 bar bestätigt?" in out
    assert "Passt das so?" in out
