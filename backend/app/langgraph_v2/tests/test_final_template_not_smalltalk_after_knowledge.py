def test_final_template_not_smalltalk_after_knowledge(monkeypatch):
    import app.langgraph_v2.sealai_graph_v2 as mod

    picked = {}

    # Hook render_template(template_name, context) to capture template choice
    def _fake_render_template(template_name, context):
        picked["template_name"] = template_name
        # Return something that downstream splitting/parsing tolerates
        return "SYSTEM\n---\nUSER"

    monkeypatch.setattr(mod, "render_template", _fake_render_template)

    payload = {
        # Required by _render_final_prompt_messages
        "template_context": {
            "goal": "smalltalk",                # force selector toward SMALLTALK_TEMPLATE initially
            "recommendation_go": False,
        },
        # Fields used by your new guard logic
        "last_node": "generic_sealing_qa_node",
        "next_action": "RUN_KNOWLEDGE",
        # Other common fields (safe defaults)
        "messages": [],
        "phase": "final",
        "thread_id": "t1",
        "tenant_id": "t",
        "user_id": "u",
    }

    _ = mod._render_final_prompt_messages(payload)

    assert "template_name" in picked, "render_template was not called; test can't verify template selection"
    assert picked["template_name"] != mod.SMALLTALK_TEMPLATE, (
        f"Expected non-smalltalk template after knowledge, but got {picked['template_name']}"
    )
