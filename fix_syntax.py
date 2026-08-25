import os

file_path = "backend/automation.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Fix the trailing duplicate args
# It currently looks like:
# """, {"trackingNumber": trackingNumber, "skipScrollSearch": skipScrollSearch}), {"trackingNumber": tracking_number, "skipScrollSearch": skip_scroll_search})
# We want to replace it with:
# """, {"trackingNumber": tracking_number, "skipScrollSearch": skip_scroll_search})

bad_str = '""", {"trackingNumber": trackingNumber, "skipScrollSearch": skipScrollSearch}), {"trackingNumber": tracking_number, "skipScrollSearch": skip_scroll_search})'
good_str = '""", {"trackingNumber": tracking_number, "skipScrollSearch": skip_scroll_search})'

content = content.replace(bad_str, good_str)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

