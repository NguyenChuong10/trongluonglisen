import os

file_path = r'd:\JMS_Helper_Complete_Updated\popup_tool.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update colors and title
old_init = '''    def __init__(self, root):
        self.root = root
        self.root.title("JMS Helper Popup")
        self.root.geometry("640x520")
        self.root.attributes("-topmost", True)  # Always on top
        self.root.configure(bg="#11111b")

        self.packages = []           # Full in-memory list mirroring the JSON
        self.rendered_tracking = set()  # Set of tracking numbers currently rendered in UI
        self.row_widgets = {}        # Map tracking -> row_frame widget
        self.last_mtime = 0
        self.spinner_idx = 0
        self.spinner_active = False

        self.colors = {
            "bg_dark": "#11111b",
            "bg_card": "#1e1e2e",
            "bg_hover": "#313244",
            "text": "#cdd6f4",
            "text_muted": "#a6adc8",
            "accent": "#cba6f7",
            "green": "#a6e3a1",
            "blue": "#89b4fa",
            "red": "#f38ba8",
            "yellow": "#f9e2af",
            "border": "#313244"
        }'''

new_init = '''    def __init__(self, root):
        self.root = root
        self.root.title("J&T Express Popup Helper")
        self.root.geometry("680x560")
        self.root.attributes("-topmost", True)  # Always on top
        self.root.configure(bg="#f4f6f9")

        self.packages = []           # Full in-memory list mirroring the JSON
        self.rendered_tracking = set()  # Set of tracking numbers currently rendered in UI
        self.row_widgets = {}        # Map tracking -> row_frame widget
        self.last_mtime = 0
        self.spinner_idx = 0
        self.spinner_active = False

        self.colors = {
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
content = content.replace(old_init, new_init)

# 2. Add scroll to top in filter_packages
old_filter = '''        if not ready:
            self._show_placeholder()
        else:
            self.placeholder_label.pack_forget()
            for pkg in ready:
                self._add_row(pkg)

        self._update_status_label()'''

new_filter = '''        if not ready:
            self._show_placeholder()
        else:
            self.placeholder_label.pack_forget()
            for pkg in ready:
                self._add_row(pkg)
            
            # Khắc phục lỗi phải lăn lên: Scroll về đầu canvas mỗi khi gõ tìm kiếm mới
            self.canvas.yview_moveto(0)

        self._update_status_label()'''
content = content.replace(old_filter, new_filter)

# 3. Fix colors that were hardcoded to dark background equivalents in setup_ui
old_setup_1 = '''        # Header frame
        header = tk.Frame(self.root, bg=self.colors["bg_dark"], height=60)
        header.pack(fill=tk.X, padx=15, pady=(10, 0))

        title_label = tk.Label(
            header,
            text="JMS DESKTOP POPUP HELPER",
            font=("Segoe UI", 12, "bold"),
            fg=self.colors["accent"],
            bg=self.colors["bg_dark"]
        )
        title_label.pack(side=tk.LEFT)'''

new_setup_1 = '''        # Header frame
        header = tk.Frame(self.root, bg=self.colors["bg_dark"], height=60)
        header.pack(fill=tk.X, padx=15, pady=(10, 0))

        title_label = tk.Label(
            header,
            text="J&T EXPRESS HELPER",
            font=("Segoe UI", 12, "bold"),
            fg=self.colors["accent"],
            bg=self.colors["bg_dark"]
        )
        title_label.pack(side=tk.LEFT)'''
content = content.replace(old_setup_1, new_setup_1)

old_btn_refresh = '''        # Refresh button
        btn_refresh = tk.Button(
            header,
            text="🔄 Làm mới",
            command=self.force_reload,
            bg=self.colors["bg_card"],
            fg=self.colors["text"],
            activebackground=self.colors["bg_hover"],
            activeforeground="#ffffff",
            bd=1,
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            padx=10,
            pady=4
        )'''

new_btn_refresh = '''        # Refresh button
        btn_refresh = tk.Button(
            header,
            text="🔄 Làm mới",
            command=self.force_reload,
            bg=self.colors["bg_card"],
            fg=self.colors["text"],
            activebackground=self.colors["bg_hover"],
            activeforeground=self.colors["accent"],
            bd=1,
            relief=tk.SOLID,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4
        )'''
content = content.replace(old_btn_refresh, new_btn_refresh)

old_btn_select_all = '''        # Select All button
        self.btn_select_all = tk.Button(
            header,
            text="📋 Chọn tất cả",
            command=self.toggle_select_all,
            bg=self.colors["bg_card"],
            fg=self.colors["text"],
            activebackground=self.colors["bg_hover"],
            activeforeground="#ffffff",
            bd=1,
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            padx=10,
            pady=4
        )'''

new_btn_select_all = '''        # Select All button
        self.btn_select_all = tk.Button(
            header,
            text="📋 Chọn tất cả",
            command=self.toggle_select_all,
            bg=self.colors["bg_card"],
            fg=self.colors["text"],
            activebackground=self.colors["bg_hover"],
            activeforeground=self.colors["accent"],
            bd=1,
            relief=tk.SOLID,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4
        )'''
content = content.replace(old_btn_select_all, new_btn_select_all)

old_btn_del = '''        # Delete Selected button
        btn_delete = tk.Button(
            header,
            text="🗑️ Xóa đã chọn",
            command=self.delete_selected,
            bg=self.colors["red"],
            fg=self.colors["bg_dark"],
            activebackground=self.colors["accent"],
            activeforeground=self.colors["bg_dark"],
            bd=0,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4
        )'''

new_btn_del = '''        # Delete Selected button
        btn_delete = tk.Button(
            header,
            text="🗑️ Xóa đã chọn",
            command=self.delete_selected,
            bg=self.colors["red"],
            fg="#ffffff",
            activebackground=self.colors["accent"],
            activeforeground="#ffffff",
            bd=0,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4
        )'''
content = content.replace(old_btn_del, new_btn_del)

old_search = '''        self.search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            bg=self.colors["bg_card"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            bd=1,
            relief=tk.FLAT,
            font=("Segoe UI", 9)
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)'''

new_search = '''        self.search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            bg=self.colors["bg_card"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            bd=1,
            relief=tk.SOLID,
            font=("Segoe UI", 10)
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)'''
content = content.replace(old_search, new_search)

old_canvas = '''        # Container frame for Canvas + Scrollbar
        container = tk.Frame(self.root, bg=self.colors["bg_dark"])
        container.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        self.canvas = tk.Canvas(container, bg=self.colors["bg_dark"], bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)

        self.scroll_frame = tk.Frame(self.canvas, bg=self.colors["bg_dark"])'''

new_canvas = '''        # Container frame for Canvas + Scrollbar
        container = tk.Frame(self.root, bg=self.colors["bg_card"], bd=1, relief=tk.SOLID)
        container.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        self.canvas = tk.Canvas(container, bg=self.colors["bg_card"], bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)

        self.scroll_frame = tk.Frame(self.canvas, bg=self.colors["bg_card"])'''
content = content.replace(old_canvas, new_canvas)

old_placeholder = '''        # Placeholder label (shown when no packages yet)
        self.placeholder_label = tk.Label(
            self.scroll_frame,
            text="Chưa có đơn hàng nào tải đầy đủ 3 ảnh + 1 video.",
            font=("Segoe UI", 10),
            fg=self.colors["text_muted"],
            bg=self.colors["bg_dark"]
        )'''

new_placeholder = '''        # Placeholder label (shown when no packages yet)
        self.placeholder_label = tk.Label(
            self.scroll_frame,
            text="Chưa có đơn hàng nào tải đầy đủ 3 ảnh + 1 video.",
            font=("Segoe UI", 10),
            fg=self.colors["text_muted"],
            bg=self.colors["bg_card"]
        )'''
content = content.replace(old_placeholder, new_placeholder)

old_copy_btn = '''        # Copy tracking button
        tk.Button(
            row_frame,
            text="📋 Copy MĐV",
            command=lambda t=tracking: self.copy_text(t, "Mã vận đơn"),
            bg=self.colors["blue"],
            fg=self.colors["bg_dark"],
            activebackground=self.colors["accent"],
            font=("Segoe UI", 8, "bold"),
            bd=0, padx=6, pady=2, cursor="hand2"
        ).pack(side=tk.LEFT, padx=5)'''

new_copy_btn = '''        # Copy tracking button
        tk.Button(
            row_frame,
            text="📋 Copy MĐV",
            command=lambda t=tracking: self.copy_text(t, "Mã vận đơn"),
            bg=self.colors["bg_card"],
            fg=self.colors["blue"],
            activebackground=self.colors["bg_hover"],
            activeforeground=self.colors["blue"],
            font=("Segoe UI", 8, "bold"),
            bd=1, relief=tk.SOLID, padx=6, pady=2, cursor="hand2"
        ).pack(side=tk.LEFT, padx=5)'''
content = content.replace(old_copy_btn, new_copy_btn)

old_weight_label = '''        # Weight label
        weight_val = str(weight) if weight is not None else "0"
        tk.Label(
            row_frame,
            text=weight_str,
            font=("Segoe UI", 10),
            fg=self.colors["text_muted"],
            bg=row_bg
        ).pack(side=tk.LEFT, padx=(12, 4))'''

new_weight_label = '''        # Weight label
        weight_val = str(weight) if weight is not None else "0"
        tk.Label(
            row_frame,
            text=weight_str,
            font=("Segoe UI", 10, "bold"),
            fg=self.colors["accent"],
            bg=row_bg
        ).pack(side=tk.LEFT, padx=(12, 4))'''
content = content.replace(old_weight_label, new_weight_label)

old_copy_weight = '''        # Copy weight button
        tk.Button(
            row_frame,
            text="📋 Cân",
            command=lambda w=weight_val, t=tracking: self.copy_weight(w, t),
            bg=self.colors["text_muted"],
            fg=self.colors["bg_dark"],
            activebackground=self.colors["accent"],
            font=("Segoe UI", 8, "bold"),
            bd=0, padx=6, pady=2, cursor="hand2"
        ).pack(side=tk.LEFT, padx=3)'''

new_copy_weight = '''        # Copy weight button
        tk.Button(
            row_frame,
            text="📋 Cân",
            command=lambda w=weight_val, t=tracking: self.copy_weight(w, t),
            bg=self.colors["bg_card"],
            fg=self.colors["text_muted"],
            activebackground=self.colors["bg_hover"],
            activeforeground=self.colors["text"],
            font=("Segoe UI", 8, "bold"),
            bd=1, relief=tk.SOLID, padx=6, pady=2, cursor="hand2"
        ).pack(side=tk.LEFT, padx=3)'''
content = content.replace(old_copy_weight, new_copy_weight)

old_jms_btn = '''        # JMS Upload button
        tk.Button(
            row_frame,
            text="🚀 JMS Upload",
            command=lambda t=tracking: self.automate_jms_upload(t),
            bg=self.colors["green"],
            fg=self.colors["bg_dark"],
            activebackground=self.colors["accent"],
            font=("Segoe UI", 9, "bold"),
            bd=0, padx=8, pady=3, cursor="hand2"
        ).pack(side=tk.RIGHT, padx=10)'''

new_jms_btn = '''        # JMS Upload button
        tk.Button(
            row_frame,
            text="🚀 JMS Upload",
            command=lambda t=tracking: self.automate_jms_upload(t),
            bg=self.colors["accent"],
            fg="#ffffff",
            activebackground=self.colors["red"],
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            bd=0, padx=8, pady=4, cursor="hand2"
        ).pack(side=tk.RIGHT, padx=10)'''
content = content.replace(old_jms_btn, new_jms_btn)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated popup_tool.py successfully!")
