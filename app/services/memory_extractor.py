import re


def extract_memory(message: str):
    """
    Extract simple user facts from a message.

    Returns:
        (key, value)
        or
        (None, None)
    """

    text = message.lower().strip()

    patterns = [
        (
            r"my favourite colour is (.+)",
            "favorite_color"
        ),
        (
            r"my favorite color is (.+)",
            "favorite_color"
        ),
        (
            r"my name is (.+)",
            "name"
        ),
        (
            r"i live in (.+)",
            "city"
        ),
        (
            r"my favourite food is (.+)",
            "favorite_food"
        ),
        (
            r"my favorite food is (.+)",
            "favorite_food"
        ),
    ]

    for pattern, key in patterns:
        match = re.search(pattern, text)

        if match:
            value = match.group(1).strip()

            return key, value

    return None, None