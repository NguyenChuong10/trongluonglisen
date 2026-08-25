import os

FILES = [
    "backend/automation.py",
    "backend/action_th1.py",
    "backend/action_th2.py",
    "backend/action_5in1.py",
    "static/debug.html"
]

REPLACEMENTS = {
    "'.chat-item'": "window.zalo_chat_item || '.chat-item'",
    '".chat-item"': 'window.zalo_chat_item || ".chat-item"',
    "'.transform-gpu'": "window.zalo_scroll_container || '.transform-gpu'",
    '".transform-gpu"': 'window.zalo_scroll_container || ".transform-gpu"',
    "'.message-view__scroll .transform-gpu'": "window.zalo_scroll_container || '.message-view__scroll .transform-gpu'",
    "'.search-message-inchat'": "window.zalo_search_inchat || '.search-message-inchat'",
    "'.message-reaction-v2-space'": "window.zalo_reaction_space || '.message-reaction-v2-space'",
    "'.conv-item, [class*=\"conv\"], .msg-item'": "window.zalo_conv_item || '.conv-item, [class*=\"conv\"], .msg-item'",
    "'.conv-item, [class*=\"conv\"], .msg-item, div, span'": "window.zalo_conv_item || '.conv-item, [class*=\"conv\"], .msg-item, div, span'",
    "'.list-chat-box-banner, [class*=\"list-chat-box-banner\"], .chat-group-topic, [class*=\"pinned-message\"]'": "window.zalo_pinned_banner || '.list-chat-box-banner, [class*=\"list-chat-box-banner\"], .chat-group-topic, [class*=\"pinned-message\"]'"
}

def process_file(filepath):
    if not os.path.exists(filepath):
        print(f"File {filepath} not found!")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    for old, new in REPLACEMENTS.items():
        content = content.replace(old, new)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Refactored selectors in {filepath}")

for f in FILES:
    process_file(f)
