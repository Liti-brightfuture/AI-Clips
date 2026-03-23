def test_money_caption_format():
    from pipeline.caption_generator import generate_caption
    script_data = {
        "hook_line": "AI is changing everything.",
        "tool_benefit": "Jasper cuts your writing time by 90%.",
    }
    caption = generate_caption(script_data, command="money")
    assert "AI is changing everything." in caption
    assert "🤖" in caption
    assert "#AItools" in caption
    assert "link in bio" in caption.lower()


def test_b2b_caption_format():
    from pipeline.caption_generator import generate_caption
    script_data = {
        "hook_line": "HubSpot costs $800/month.",
        "data_point": "Monday.com costs 75% less.",
    }
    caption = generate_caption(script_data, command="b2b")
    assert "HubSpot costs $800/month." in caption
    assert "💼" in caption
    assert "#SaaS" in caption
    assert "Monday.com costs 75% less." in caption


def test_money_caption_no_data_point():
    from pipeline.caption_generator import generate_caption
    script_data = {
        "hook_line": "This tool changed my workflow.",
        "tool_benefit": "It saves 3 hours per day.",
    }
    caption = generate_caption(script_data, command="money")
    assert "data_point" not in caption


def test_b2b_caption_no_tool_benefit():
    from pipeline.caption_generator import generate_caption
    script_data = {
        "hook_line": "Pipedrive closes more deals.",
        "data_point": "Users report 28% more closed deals.",
    }
    caption = generate_caption(script_data, command="b2b")
    assert "tool_benefit" not in caption
