import os

file_path = "backend/automation.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

bad_str = """                        if (targetBubble) {
                            targetBubble.scrollIntoView({ block: 'center' });
                            return { success: true };
                        }"""

good_str = """                        if (targetBubble) {
                            targetBubble.classList.add('zalo-video-temp-target');
                            targetBubble.scrollIntoView({ block: 'center' });
                            return { success: true };
                        }"""

content = content.replace(bad_str, good_str)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed tag success class")
