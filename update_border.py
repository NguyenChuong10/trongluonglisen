import os

file_path = r'd:\JMS_Helper_Complete_Updated\popup_tool.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update green color to a darker one
old_colors = '''        self.colors = {
            "bg_dark": "#f4f6f9",
            "bg_card": "#ffffff",
            "bg_hover": "#fff0f1",
            "text": "#2d3436",
            "text_muted": "#636e72",
            "accent": "#E61B23",
            "green": "#00b894",
            "blue": "#0984e3",
            "red": "#d63031",
            "yellow": "#fdcb6e",
            "border": "#dcdde1"
        }'''

new_colors = '''        self.colors = {
            "bg_dark": "#f4f6f9",
            "bg_card": "#ffffff",
            "bg_hover": "#fff0f1",
            "text": "#2d3436",
            "text_muted": "#636e72",
            "accent": "#E61B23",
            "green": "#008000",  # Darker green for visibility
            "blue": "#0984e3",
            "red": "#d63031",
            "yellow": "#fdcb6e",
            "border": "#dcdde1"
        }'''
content = content.replace(old_colors, new_colors)

# 2. Update highlightthickness from 1 to 2
old_thickness = '''        row_frame = tk.Frame(
            self.scroll_frame,
            bg=row_bg,
            bd=1,
            relief=tk.FLAT,
            highlightbackground=self.colors["green"] if copied else self.colors["border"],
            highlightthickness=1,
            padx=10,
            pady=8
        )'''

new_thickness = '''        row_frame = tk.Frame(
            self.scroll_frame,
            bg=row_bg,
            bd=1,
            relief=tk.FLAT,
            highlightbackground=self.colors["green"] if copied else self.colors["border"],
            highlightthickness=2,
            padx=10,
            pady=8
        )'''
content = content.replace(old_thickness, new_thickness)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
