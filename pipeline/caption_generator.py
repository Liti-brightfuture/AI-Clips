MONEY_HASHTAGS = "#AItools #productivity #ChatGPT #artificialintelligence #techhacks"
B2B_HASHTAGS = "#SaaS #business #startup #productivity #entrepreneur"


def generate_caption(script_data: dict, command: str) -> str:
    """
    Build a Telegram/social caption from script JSON fields.

    Args:
        script_data: Dict with hook_line and tool_benefit (money) or data_point (b2b).
        command: "money" or "b2b".

    Returns:
        Formatted caption string ready to post alongside the video.
    """
    hook = script_data["hook_line"]

    if command == "money":
        benefit = script_data["tool_benefit"]
        return (
            f"{hook} 🤖\n"
            f"{benefit}\n"
            f"Try free → link in bio\n"
            f"{MONEY_HASHTAGS}"
        )
    else:
        data_point = script_data["data_point"]
        return (
            f"{hook} 💼\n"
            f"{data_point}\n"
            f"Full breakdown → link in bio\n"
            f"{B2B_HASHTAGS}"
        )
