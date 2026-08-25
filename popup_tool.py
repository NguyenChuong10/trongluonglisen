import os
import sys
import json
import time
import threading
import platform
from filelock import FileLock
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox

try:
    import win32gui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

# Set output encoding to UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Constants & Paths
if hasattr(sys, '_MEIPASS'):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SCANNED_FILE = os.path.join(DATA_DIR, "scanned_packages.json")

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# CustomTkinter setup
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class JMSPopupApp:
    def __init__(self, root):
        self.root = root
        self.root.title("JMS Helper Popup - J&T Express")
        self.root.geometry("720x620")
        self.root.attributes("-topmost", True)  # Always on top

        self.packages = []           # Full in-memory list mirroring the JSON
        self.rendered_tracking = set()  # Set of tracking numbers currently rendered in UI
        self.row_widgets = {}        # Map tracking -> row_frame widget
        self.last_mtime = 0
        self.spinner_idx = 0
        self.spinner_active = False
        self.current_tab = "jms"
        self.current_page = 1
        self.page_size = 30

        # Theme Colors (Light Mode, Dark Mode)
        self.colors = {
            "bg_dark": ("#f1f5f9", "#0f172a"),       # Slate 100 / Slate 900
            "bg_card": ("#ffffff", "#1e293b"),       # White / Slate 800
            "bg_hover": ("#e2e8f0", "#334155"),      # Slate 200 / Slate 700
            "bg_copied": ("#e6f4ea", "#0f2e22"),     # Light Green / Dark Emerald
            "bg_copied_hover": ("#d2ebd9", "#143d2d"), # Medium Green / Lighter Emerald
            "text": ("#0f172a", "#f8fafc"),          # Slate 900 / Slate 50
            "text_muted": ("#64748b", "#94a3b8"),    # Slate 500 / Slate 400
            "accent": ("#ef4444", "#ef4444"),        # J&T Red/Coral
            "green": ("#10b981", "#10b981"),         # Emerald Green
            "blue": ("#3b82f6", "#3b82f6"),          # Dodger Blue
            "red": ("#ef4444", "#ef4444"),           # Vibrant Red
            "yellow": ("#f59e0b", "#f59e0b"),        # Amber Yellow
            "border": ("#cbd5e1", "#334155")         # Slate 300 / Slate 700
        }

        self.root.configure(fg_color=self.colors["bg_dark"])
        self.setup_ui()
        self.initial_load()
        self.check_updates_loop()

    def get_hover_color(self, bg):
        if bg == self.colors["bg_card"]:
            return self.colors["bg_hover"]
        elif bg == self.colors["red"]:
            return ("#f87171", "#f87171")
        elif bg == self.colors["accent"]:
            return ("#f87171", "#f87171")
        elif bg == self.colors["yellow"]:
            return ("#fbbf24", "#fbbf24")
        elif bg == self.colors["blue"]:
            return ("#60a5fa", "#60a5fa")
        elif bg == self.colors["bg_dark"]:
            return self.colors["bg_hover"]
        return bg

    def create_modern_button(self, parent, text, command, bg, fg, font=("Segoe UI", 9, "bold"), width=95, height=28, corner_radius=6):
        btn = ctk.CTkButton(
            parent,
            text=text,
            command=command,
            fg_color=bg,
            hover_color=self.get_hover_color(bg),
            text_color=fg,
            font=ctk.CTkFont(family=font[0], size=font[1], weight="bold" if "bold" in font else "normal"),
            width=width,
            height=height,
            corner_radius=corner_radius
        )
        return btn

    def setup_ui(self):
        # Header frame
        self.header = ctk.CTkFrame(self.root, fg_color=self.colors["bg_dark"], height=60, corner_radius=0)
        self.header.pack(fill=tk.X, padx=15, pady=(15, 0))
        self.header.bind("<Configure>", self.on_header_configure)

        # Title container
        self.title_container = ctk.CTkFrame(self.header, fg_color=self.colors["bg_dark"], corner_radius=0)
        self.title_container.pack(side=tk.LEFT)

        self.title_label = ctk.CTkLabel(
            self.title_container,
            text="J&T EXPRESS HELPER",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self.colors["accent"]
        )
        self.title_label.pack(side=tk.LEFT)

        self.desc_label = ctk.CTkLabel(
            self.title_container,
            text=" (Always on top)",
            font=ctk.CTkFont(family="Segoe UI", size=9, slant="italic"),
            text_color=self.colors["text_muted"]
        )
        self.desc_label.pack(side=tk.LEFT, pady=4)

        # Spinner label
        self.spinner_label = ctk.CTkLabel(
            self.header,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self.colors["accent"]
        )
        self.spinner_label.pack(side=tk.LEFT, padx=(8, 0))

        # Status label
        self.status_label = ctk.CTkLabel(
            self.header,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=self.colors["text_muted"]
        )
        self.status_label.pack(side=tk.LEFT, padx=(8, 0))

        # Theme Switch
        self.theme_switch_var = ctk.StringVar(value="dark")
        self.theme_switch = ctk.CTkSwitch(
            self.header,
            text="Tối 🌙",
            command=self.toggle_theme,
            variable=self.theme_switch_var,
            onvalue="dark",
            offvalue="light",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            progress_color=self.colors["accent"],
            text_color=self.colors["text"]
        )
        self.theme_switch.pack(side=tk.RIGHT, padx=(10, 0))

        # Refresh button
        self.btn_refresh = self.create_modern_button(self.header, "🔄 Làm mới", self.force_reload, self.colors["bg_card"], self.colors["text"])
        self.btn_refresh.pack(side=tk.RIGHT, padx=2)

        # Select All button
        self.btn_select_all = self.create_modern_button(self.header, "📋 Chọn tất cả", self.toggle_select_all, self.colors["bg_card"], self.colors["text"], width=110)
        self.btn_select_all.pack(side=tk.RIGHT, padx=2)

        # Delete Selected button
        self.btn_delete = self.create_modern_button(self.header, "🗑️ Xóa đã chọn", self.delete_selected, self.colors["red"], "#ffffff", width=110)
        self.btn_delete.pack(side=tk.RIGHT, padx=2)

        # Separator line
        self.sep = ctk.CTkFrame(self.root, height=1, fg_color=self.colors["border"], corner_radius=0)
        self.sep.pack(fill=tk.X, padx=15, pady=(8, 0))

        # Search frame
        self.search_frame = ctk.CTkFrame(self.root, fg_color=self.colors["bg_dark"], corner_radius=0)
        self.search_frame.pack(fill=tk.X, padx=15, pady=(10, 0))

        self.search_title_label = ctk.CTkLabel(
            self.search_frame,
            text="🔍 Tìm kiếm MĐV:",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=self.colors["accent"]
        )
        self.search_title_label.pack(side=tk.LEFT, padx=(0, 5))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.filter_packages())
        
        self.search_entry = ctk.CTkEntry(
            self.search_frame,
            textvariable=self.search_var,
            placeholder_text="Nhập mã vận đơn...",
            fg_color=self.colors["bg_card"],
            text_color=self.colors["text"],
            border_color=self.colors["border"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=6,
            height=30
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_clear_search = self.create_modern_button(
            self.search_frame,
            text="✕",
            command=lambda: self.search_var.set(""),
            bg=self.colors["bg_card"],
            fg=self.colors["text_muted"],
            width=30, height=30,
            corner_radius=6
        )
        self.btn_clear_search.pack(side=tk.LEFT, padx=(4, 0))

        # Tabs Segmented Control
        self.tabs_frame = ctk.CTkFrame(self.root, fg_color=self.colors["bg_dark"], corner_radius=0)
        self.tabs_frame.pack(fill=tk.X, padx=15, pady=(10, 0))

        self.tab_button = ctk.CTkSegmentedButton(
            self.tabs_frame,
            values=["🚀 ĐƠN JMS UPLOAD (0)", "🛠️ ĐƠN THỦ CÔNG (0)"],
            command=self.switch_tab,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=self.colors["bg_card"],
            selected_color=self.colors["accent"],
            selected_hover_color="#f87171",
            text_color=self.colors["text_muted"],
            corner_radius=6
        )
        self.tab_button.pack(fill=tk.X, expand=True)
        self.tab_button.set("🚀 ĐƠN JMS UPLOAD (0)")

        # Scrollable Frame
        self.scroll_frame = ctk.CTkScrollableFrame(
            self.root,
            fg_color=self.colors["bg_dark"],
            label_text=None,
            corner_radius=8
        )

        # Footer build author info
        self.footer = ctk.CTkFrame(self.root, fg_color=self.colors["bg_dark"], corner_radius=0)
        self.footer.pack(fill=tk.X, side=tk.BOTTOM, padx=15, pady=(0, 10))
        
        self.author_label = ctk.CTkLabel(
            self.footer,
            text="Người build App : Nguyễn Đình Nguyên Chương",
            font=ctk.CTkFont(family="Segoe UI", size=8, slant="italic"),
            text_color=self.colors["text_muted"]
        )
        self.author_label.pack(side=tk.RIGHT)

        # Pagination Frame
        self.pagination_frame = ctk.CTkFrame(self.root, fg_color=self.colors["bg_dark"], height=35, corner_radius=0)
        self.pagination_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=(0, 5))

        self.btn_prev_page = self.create_modern_button(
            self.pagination_frame,
            text="◀ Trước",
            command=self.prev_page,
            bg=self.colors["bg_card"],
            fg=self.colors["text"],
            width=70, height=26
        )
        self.btn_prev_page.pack(side=tk.LEFT, padx=5)

        self.page_label = ctk.CTkLabel(
            self.pagination_frame,
            text="Trang 1 / 1",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=self.colors["text"]
        )
        self.page_label.pack(side=tk.LEFT, padx=10)

        self.btn_next_page = self.create_modern_button(
            self.pagination_frame,
            text="Sau ▶",
            command=self.next_page,
            bg=self.colors["bg_card"],
            fg=self.colors["text"],
            width=70, height=26
        )
        self.btn_next_page.pack(side=tk.LEFT, padx=5)

        self.total_label = ctk.CTkLabel(
            self.pagination_frame,
            text="Tổng cộng: 0 đơn",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=self.colors["text_muted"]
        )
        self.total_label.pack(side=tk.RIGHT, padx=10)

        # Pack scroll_frame in remaining center space
        self.scroll_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        # Placeholder label
        self.placeholder_label = ctk.CTkLabel(
            self.scroll_frame,
            text="Chưa có đơn hàng nào tải đầy đủ 3 ảnh + 1 video.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=self.colors["text_muted"]
        )

    def toggle_theme(self):
        mode = self.theme_switch_var.get()
        if mode == "dark":
            ctk.set_appearance_mode("dark")
            self.theme_switch.configure(text="Tối 🌙")
        else:
            ctk.set_appearance_mode("light")
            self.theme_switch.configure(text="Sáng ☀️")

    def on_header_configure(self, event):
        width = event.width
        if width < 620:
            self.title_container.pack_forget()
        else:
            self.title_container.pack(side=tk.LEFT, before=self.spinner_label)

    def _show_placeholder(self):
        try:
            if not self.placeholder_label.winfo_exists():
                self.placeholder_label = ctk.CTkLabel(
                    self.scroll_frame,
                    text="Chưa có đơn hàng nào tải đầy đủ 3 ảnh + 1 video.",
                    font=ctk.CTkFont(family="Segoe UI", size=10),
                    text_color=self.colors["text_muted"]
                )
            self.placeholder_label.pack(pady=40)
        except Exception:
            pass

    def _update_status_label(self):
        ready_count = len(self.rendered_tracking)
        if ready_count == 0:
            self.status_label.configure(text="")
        else:
            if self.current_tab == "jms":
                self.status_label.configure(text=f"| {ready_count} đơn sẵn sàng")
            else:
                self.status_label.configure(text=f"| {ready_count} đơn lỗi cần xử lý")

    def toggle_select_all(self):
        if self.current_tab == "jms":
            ready_packages = [p for p in self.packages if isinstance(p, dict) and p.get("localStatus") == "Đã tải về"]
        else:
            ready_packages = [p for p in self.packages if isinstance(p, dict) and str(p.get("localStatus", "")).startswith("Lỗi")]

        if not ready_packages:
            return
            
        unchecked_exists = any(not p.get("copied", False) for p in ready_packages)
        target_state = True if unchecked_exists else False

        for p in ready_packages:
            p["copied"] = target_state

        for trk, row_frame in self.row_widgets.items():
            if hasattr(row_frame, "chk_widget"):
                if target_state:
                    row_frame.chk_widget.select()
                else:
                    row_frame.chk_widget.deselect()
            self.style_row_state(row_frame, trk, target_state)

        self._update_select_all_btn_text()
        self._save_packages_to_disk()

    def _update_select_all_btn_text(self):
        if self.current_tab == "jms":
            ready_packages = [p for p in self.packages if isinstance(p, dict) and p.get("localStatus") == "Đã tải về"]
        else:
            ready_packages = [p for p in self.packages if isinstance(p, dict) and str(p.get("localStatus", "")).startswith("Lỗi")]

        if not ready_packages:
            self.btn_select_all.configure(text="📋 Chọn tất cả")
            return
        all_checked = all(p.get("copied", False) for p in ready_packages)
        if all_checked:
            self.btn_select_all.configure(text="🔓 Bỏ chọn tất cả")
        else:
            self.btn_select_all.configure(text="📋 Chọn tất cả")

    def _save_packages_to_disk(self):
        try:
            with FileLock(SCANNED_FILE + '.lock', timeout=5), open(SCANNED_FILE, "w", encoding="utf-8") as f:
                json.dump(self.packages, f, ensure_ascii=False, indent=4)
            self.last_mtime = os.path.getmtime(SCANNED_FILE)
        except Exception as e:
            print(f"[Popup] _save_packages_to_disk error: {e}")

    def delete_selected(self):
        if self.current_tab == "jms":
            ready_packages = [p for p in self.packages if isinstance(p, dict) and p.get("localStatus") == "Đã tải về"]
        else:
            ready_packages = [p for p in self.packages if isinstance(p, dict) and str(p.get("localStatus", "")).startswith("Lỗi")]

        selected = [p for p in ready_packages if p.get("copied", False)]

        if not selected:
            messagebox.showwarning("Không có đơn chọn", "Vui lòng tích chọn (Đã copy) các đơn hàng cần xóa.")
            return

        confirm = messagebox.askyesno(
            "Xác nhận xóa đơn",
            f"Bạn có chắc chắn muốn xóa {len(selected)} đơn hàng đã chọn?\n\n"
            "⚠️ LƯU Ý: Hành động này sẽ xóa vĩnh viễn dữ liệu đơn hàng và toàn bộ ảnh/video liên quan trên ổ đĩa."
        )

        if not confirm:
            return

        import shutil
        deleted_count = 0

        for pkg in selected:
            trk = pkg.get("trackingNumber")
            folder_name = pkg.get("folderName")
            
            if folder_name:
                folder_path = os.path.join(DATA_DIR, folder_name)
                if os.path.exists(folder_path) and os.path.isdir(folder_path):
                    try:
                        shutil.rmtree(folder_path)
                    except Exception as err:
                        print(f"[Popup] Lỗi xóa thư mục {folder_path}: {err}")

            row_frame = self.row_widgets.get(trk)
            if row_frame:
                row_frame.destroy()
                self.row_widgets.pop(trk, None)

            self.rendered_tracking.discard(trk)
            self.packages = [p for p in self.packages if p.get("trackingNumber") != trk]
            deleted_count += 1

        self._save_packages_to_disk()
        self.filter_packages(reset_scroll=False)
        self.show_toast(f"Đã xóa thành công {deleted_count} đơn hàng!")

    def style_row_state(self, row_frame, tracking, is_copied):
        if is_copied:
            bg = self.colors["bg_copied"]
            border_color = self.colors["green"]
            border_width = 2
        else:
            bg = self.colors["bg_card"]
            border_color = self.colors["border"]
            border_width = 1
            
        row_frame.configure(
            fg_color=bg,
            border_color=border_color,
            border_width=border_width
        )
        
        folder_badge_text = f"#{self.get_folder_name_by_tracking(tracking)}"
        for child in row_frame.winfo_children():
            cls = child.winfo_class()
            if cls == "CTkLabel":
                if child.cget("text") == folder_badge_text:
                    continue
                child.configure(fg_color=bg)
            elif cls == "CTkCheckBox":
                child.configure(fg_color=self.colors["green"], hover_color=self.colors["bg_hover"])

    def initial_load(self):
        if not os.path.exists(SCANNED_FILE):
            self._show_placeholder()
            return
        try:
            with FileLock(SCANNED_FILE + '.lock', timeout=5), open(SCANNED_FILE, "r", encoding="utf-8") as f:
                self.packages = json.load(f)
        except Exception:
            self.packages = []

        if not isinstance(self.packages, list):
            if isinstance(self.packages, dict):
                self.packages = list(self.packages.values())
            else:
                self.packages = []

        self.filter_packages()

    def force_reload(self):
        copied_map = {}
        for p in self.packages:
            if isinstance(p, dict) and p.get("trackingNumber"):
                copied_map[p["trackingNumber"]] = p.get("copied", False)

        for child in self.scroll_frame.winfo_children():
            child.destroy()
        self.rendered_tracking.clear()
        self.row_widgets.clear()

        if not os.path.exists(SCANNED_FILE):
            self._show_placeholder()
            return
        try:
            with FileLock(SCANNED_FILE + '.lock', timeout=5), open(SCANNED_FILE, "r", encoding="utf-8") as f:
                self.packages = json.load(f)
        except Exception:
            self.packages = []

        if not isinstance(self.packages, list):
            if isinstance(self.packages, dict):
                self.packages = list(self.packages.values())
            else:
                self.packages = []

        for pkg in self.packages:
            if isinstance(pkg, dict) and pkg.get("trackingNumber"):
                trk = pkg.get("trackingNumber")
                if trk in copied_map and copied_map[trk]:
                    pkg["copied"] = True

        self.filter_packages()

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.filter_packages(reset_scroll=False)
            try:
                self.scroll_frame._parent_canvas.yview_moveto(0.0)
            except Exception:
                pass

    def next_page(self):
        ready = [p for p in self.packages if isinstance(p, dict) and (p.get("localStatus") == "Đã tải về" or str(p.get("localStatus", "")).startswith("Lỗi"))]
        if self.current_tab == "jms":
            ready = [p for p in ready if p.get("localStatus") == "Đã tải về"]
        else:
            ready = [p for p in ready if str(p.get("localStatus", "")).startswith("Lỗi")]

        query = self.search_var.get().strip().lower()
        if query:
            ready = [p for p in ready if query in p.get("trackingNumber", "").lower()]

        import math
        total_pages = math.ceil(len(ready) / self.page_size) or 1
        if self.current_page < total_pages:
            self.current_page += 1
            self.filter_packages(reset_scroll=False)
            try:
                self.scroll_frame._parent_canvas.yview_moveto(0.0)
            except Exception:
                pass

    def filter_packages(self, reset_scroll=True):
        if reset_scroll:
            self.current_page = 1

        query = self.search_var.get().strip().lower()

        ready = [p for p in self.packages if isinstance(p, dict) and (p.get("localStatus") == "Đã tải về" or str(p.get("localStatus", "")).startswith("Lỗi"))]

        if self.current_tab == "jms":
            ready = [p for p in ready if p.get("localStatus") == "Đã tải về"]
        else:
            ready = [p for p in ready if str(p.get("localStatus", "")).startswith("Lỗi")]

        if query:
            ready = [p for p in ready if query in p.get("trackingNumber", "").lower()]

        total_items = len(ready)
        import math
        total_pages = math.ceil(total_items / self.page_size) or 1

        if self.current_page > total_pages:
            self.current_page = total_pages
        if self.current_page < 1:
            self.current_page = 1

        page_data = ready[(self.current_page - 1) * self.page_size : self.current_page * self.page_size]

        # Clean old widgets to save memory and avoid handles limit
        for trk, row_frame in list(self.row_widgets.items()):
            row_frame.destroy()
        self.row_widgets.clear()
        self.rendered_tracking.clear()

        # Render page rows
        for pkg in page_data:
            self._add_row(pkg)

        if not ready:
            self._show_placeholder()
        else:
            if self.placeholder_label.winfo_exists():
                self.placeholder_label.pack_forget()

        # Update pagination display & buttons
        self.page_label.configure(text=f"Trang {self.current_page} / {total_pages}")
        self.total_label.configure(text=f"Tổng cộng: {total_items} đơn")

        if self.current_page <= 1:
            self.btn_prev_page.configure(state="disabled")
        else:
            self.btn_prev_page.configure(state="normal")

        if self.current_page >= total_pages:
            self.btn_next_page.configure(state="disabled")
        else:
            self.btn_next_page.configure(state="normal")

        self._update_status_label()
        self._update_select_all_btn_text()
        self.update_tab_ui()

        # Reset scroll view to top when filtering/switching tabs
        if reset_scroll:
            try:
                self.scroll_frame._parent_canvas.yview_moveto(0.0)
            except Exception:
                pass

    def switch_tab(self, selected_value):
        if "JMS UPLOAD" in selected_value:
            self.current_tab = "jms"
        else:
            self.current_tab = "manual"
        self.filter_packages()

    def update_tab_ui(self):
        jms_count = len([p for p in self.packages if isinstance(p, dict) and p.get("localStatus") == "Đã tải về"])
        manual_count = len([p for p in self.packages if isinstance(p, dict) and str(p.get("localStatus", "")).startswith("Lỗi")])

        self.tab_button.configure(
            values=[f"🚀 ĐƠN JMS UPLOAD ({jms_count})", f"🛠️ ĐƠN THỦ CÔNG ({manual_count})"]
        )

    def check_updates_loop(self):
        try:
            if os.path.exists(SCANNED_FILE):
                mtime = os.path.getmtime(SCANNED_FILE)
                if mtime != self.last_mtime:
                    self.last_mtime = mtime
                    self._incremental_update()
        except Exception as e:
            print(f"[Popup] check_updates_loop error: {e}")
        self.root.after(1000, self.check_updates_loop)

    def _incremental_update(self):
        try:
            with FileLock(SCANNED_FILE + '.lock', timeout=5), open(SCANNED_FILE, "r", encoding="utf-8") as f:
                new_packages = json.load(f)
        except Exception:
            return

        if not isinstance(new_packages, list):
            if isinstance(new_packages, dict):
                new_packages = list(new_packages.values())
            else:
                new_packages = []

        existing_trk_set = {p.get("trackingNumber") for p in self.packages if isinstance(p, dict) and p.get("trackingNumber")}
        len_before = len(existing_trk_set)

        for pkg in new_packages:
            if not isinstance(pkg, dict):
                continue
            trk = pkg.get("trackingNumber")
            if not trk:
                continue
            if trk not in existing_trk_set:
                self.packages.append(pkg)
                existing_trk_set.add(trk)
            else:
                mem_pkg = next((p for p in self.packages if isinstance(p, dict) and p.get("trackingNumber") == trk), None)
                if mem_pkg:
                    mem_copied = mem_pkg.get("copied", False)
                    mem_pkg.update(pkg)
                    if mem_copied:
                        mem_pkg["copied"] = True

        has_new = len(self.packages) > len_before
        self.filter_packages(reset_scroll=False)

        if has_new:
            self._show_spinner()
            self._update_status_label()
        self._update_select_all_btn_text()

    def _show_spinner(self):
        if self.spinner_active:
            return
        self.spinner_active = True
        self._animate_spinner(frames=8)

    def _animate_spinner(self, frames):
        if frames <= 0:
            self.spinner_label.configure(text="")
            self.spinner_active = False
            return
        self.spinner_idx = (self.spinner_idx + 1) % len(SPINNER_FRAMES)
        self.spinner_label.configure(text=SPINNER_FRAMES[self.spinner_idx])
        self.root.after(80, lambda: self._animate_spinner(frames - 1))

    def _add_row(self, pkg):
        tracking = pkg.get("trackingNumber", "")
        if not tracking or tracking in self.rendered_tracking:
            return

        self.rendered_tracking.add(tracking)
        self._render_row(pkg)

    def _render_row(self, pkg):
        tracking = pkg.get("trackingNumber", "")
        weight = pkg.get("weight")
        weight_str = f"{weight} kg" if weight is not None else "0 kg"
        folder_idx = pkg.get("folderName") or "?"
        copied = pkg.get("copied", False)

        local_status = pkg.get("localStatus", "")
        is_error = str(local_status).startswith("Lỗi") or local_status == "Chưa tải về"

        row_bg = self.colors["bg_copied"] if copied else self.colors["bg_card"]
        row_frame = ctk.CTkFrame(
            self.scroll_frame,
            fg_color=row_bg,
            border_color=self.colors["green"] if copied else self.colors["border"],
            border_width=2 if copied else 1,
            corner_radius=8
        )
        row_frame.pack(fill=tk.X, pady=4, padx=5)

        self.row_widgets[tracking] = row_frame

        # Folder badge label
        badge_label = ctk.CTkLabel(
            row_frame,
            text=f"#{folder_idx}",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            fg_color=self.colors["accent"] if copied else ("#e2e8f0", "#0f172a"),
            text_color="#ffffff" if copied else self.colors["accent"],
            corner_radius=4,
            width=40, height=22
        )
        badge_label.pack(side=tk.LEFT, padx=(10, 10), pady=10)

        # Tracking number label
        tk_label = ctk.CTkLabel(
            row_frame,
            text=tracking,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=self.colors["text"],
            fg_color="transparent"
        )
        tk_label.pack(side=tk.LEFT, padx=5)

        # Copy tracking button (CTk button styling)
        self.btn_copy_trk = self.create_modern_button(
            row_frame,
            text="📋 Copy MĐV",
            command=lambda t=tracking: self.copy_text(t, "Mã vận đơn"),
            bg=self.colors["bg_dark"],
            fg=self.colors["blue"],
            font=("Segoe UI", 8, "bold")
        )
        self.btn_copy_trk.pack(side=tk.LEFT, padx=5)

        # Weight label
        weight_val = str(weight) if weight is not None else "0"
        w_lbl = ctk.CTkLabel(
            row_frame,
            text=weight_str,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=self.colors["accent"],
            fg_color="transparent"
        )
        w_lbl.pack(side=tk.LEFT, padx=(12, 4))

        # Copy weight button (CTk Button styling)
        self.btn_copy_w = self.create_modern_button(
            row_frame,
            text="📋 Cân",
            command=lambda w=weight_val, t=tracking: self.copy_weight(w, t),
            bg=self.colors["bg_dark"],
            fg=self.colors["text_muted"],
            font=("Segoe UI", 8, "bold"),
            width=65
        )
        self.btn_copy_w.pack(side=tk.LEFT, padx=3)

        # "Đã copy" checkbox styled for ctk
        chk = ctk.CTkCheckBox(
            row_frame,
            text="Đã copy",
            command=lambda t=tracking, c=None: self.toggle_copied_state(tracking, chk.get()),
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color=self.colors["green"],
            hover_color=self.colors["bg_hover"],
            text_color=self.colors["text"],
            width=20, height=20,
            corner_radius=4
        )
        chk.pack(side=tk.RIGHT, padx=15)
        if copied:
            chk.select()
        row_frame.chk_widget = chk

        if is_error:
            # Manual Button (Amber yellow)
            self.btn_action = self.create_modern_button(
                row_frame,
                text="🛠️ Thủ công",
                command=lambda t=tracking: self.manual_jms_helper(t),
                bg=self.colors["yellow"],
                fg=self.colors["bg_dark"],
                font=("Segoe UI", 9, "bold")
            )
            self.btn_action.pack(side=tk.RIGHT, padx=10)
            
            # Label saying error status details
            err_text = str(local_status) if local_status else "⚠️ Lỗi tải"
            err_lbl = ctk.CTkLabel(
                row_frame,
                text=err_text,
                font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                text_color=self.colors["red"],
                fg_color="transparent"
            )
            err_lbl.pack(side=tk.RIGHT, padx=5)
        else:
            # JMS Upload button (J&T Coral Red)
            self.btn_action = self.create_modern_button(
                row_frame,
                text="🚀 JMS Upload",
                command=lambda t=tracking: self.automate_jms_upload(t),
                bg=self.colors["accent"],
                fg="#ffffff",
                font=("Segoe UI", 9, "bold")
            )
            self.btn_action.pack(side=tk.RIGHT, padx=10)

        # Card Hover effects
        def on_enter(e):
            pkg = next((p for p in self.packages if p.get("trackingNumber") == tracking), None)
            is_cp = pkg.get("copied", False) if pkg else False
            new_bg = self.colors["bg_copied_hover"] if is_cp else self.colors["bg_hover"]
            row_frame.configure(fg_color=new_bg)

        def on_leave(e):
            pkg = next((p for p in self.packages if p.get("trackingNumber") == tracking), None)
            is_cp = pkg.get("copied", False) if pkg else False
            new_bg = self.colors["bg_copied"] if is_cp else self.colors["bg_card"]
            row_frame.configure(fg_color=new_bg)

        row_frame.bind("<Enter>", on_enter)
        row_frame.bind("<Leave>", on_leave)

    def manual_jms_helper(self, tracking_number):
        weight_val = "0"
        for pkg in self.packages:
            if pkg.get("trackingNumber") == tracking_number:
                weight_val = str(pkg.get("weight") if pkg.get("weight") is not None else "0")
                break
                
        self.root.clipboard_clear()
        self.root.clipboard_append(tracking_number)
        
        self.toggle_copied_state(tracking_number, True)
        self.show_toast(f"Đã copy Mã: {tracking_number}")
        
        messagebox.showinfo(
            "Thao tác thủ công",
            f"Đơn hàng này không có hình ảnh hoặc video làm bằng chứng trên Zalo.\n\n"
            f"👉 Đã copy Mã vận đơn: {tracking_number} (Bạn có thể dán bằng Ctrl+V)\n"
            f"👉 Số ký (Cân nặng): {weight_val} kg (Vui lòng tự nhập tay)\n\n"
            "Vui lòng tự tìm kiếm đơn hàng trên JMS và thực hiện đối soát thủ công!"
        )

    def copy_text(self, text, type_name):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.toggle_copied_state(text, True)
        self.show_toast(f"Đã copy {type_name}: {text}")

    def copy_weight(self, weight_val, tracking_number):
        self.root.clipboard_clear()
        self.root.clipboard_append(weight_val)
        self.toggle_copied_state(tracking_number, True)
        self.show_toast(f"Đã copy Cân nặng: {weight_val} kg")

    def show_toast(self, message):
        toast = ctk.CTkToplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(fg_color="#2ecc71")

        label = ctk.CTkLabel(toast, text=message, text_color="#ffffff", fg_color="#2ecc71",
                             font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"))
        label.pack(padx=15, pady=8)

        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 300) // 2
        y = self.root.winfo_y() + self.root.winfo_height() - 60
        toast.geometry(f"+{x}+{y}")
        self.root.after(1500, toast.destroy)

    def toggle_copied_state(self, tracking_number, is_copied):
        for pkg in self.packages:
            if pkg.get("trackingNumber") == tracking_number:
                pkg["copied"] = is_copied
                break

        try:
            disk_packages = []
            if os.path.exists(SCANNED_FILE):
                with FileLock(SCANNED_FILE + '.lock', timeout=5), open(SCANNED_FILE, "r", encoding="utf-8") as f:
                    try:
                        disk_packages = json.load(f)
                    except Exception:
                        disk_packages = self.packages
            else:
                disk_packages = self.packages

            found = False
            for p in disk_packages:
                if p.get("trackingNumber") == tracking_number:
                    p["copied"] = is_copied
                    found = True
                    break
            
            if not found:
                pkg_to_add = next((p for p in self.packages if p.get("trackingNumber") == tracking_number), None)
                if pkg_to_add:
                    disk_packages.append(pkg_to_add)

            with FileLock(SCANNED_FILE + '.lock', timeout=5), open(SCANNED_FILE, "w", encoding="utf-8") as f:
                json.dump(disk_packages, f, ensure_ascii=False, indent=4)
            self.last_mtime = os.path.getmtime(SCANNED_FILE)
            self.packages = disk_packages
        except Exception as e:
            print(f"[Popup] toggle_copied_state write error: {e}")

        row_frame = self.row_widgets.get(tracking_number)
        if not row_frame:
            return

        if hasattr(row_frame, "chk_widget"):
            if is_copied:
                row_frame.chk_widget.select()
            else:
                row_frame.chk_widget.deselect()

        self.style_row_state(row_frame, tracking_number, is_copied)

    def get_folder_name_by_tracking(self, tracking_number):
        for pkg in self.packages:
            if pkg.get("trackingNumber") == tracking_number:
                return pkg.get("folderName") or "?"
        return "?"

    def automate_jms_upload(self, tracking_number):
        if not HAS_WIN32:
            messagebox.showwarning("Không hỗ trợ", "Tính năng tự động upload chỉ hỗ trợ trên Windows.")
            return

        package_dir = None
        if os.path.exists(DATA_DIR):
            for item in os.listdir(DATA_DIR):
                item_path = os.path.join(DATA_DIR, item)
                if os.path.isdir(item_path):
                    if os.path.exists(os.path.join(item_path, f"{tracking_number}.txt")):
                        package_dir = item_path
                        break

        if not package_dir:
            fallback = os.path.join(DATA_DIR, tracking_number)
            if os.path.exists(fallback) and os.path.isdir(fallback):
                package_dir = fallback

        if not package_dir:
            messagebox.showwarning(
                "Không tìm thấy thư mục",
                f"Thư mục chứa ảnh/video của mã đơn {tracking_number} không tồn tại."
            )
            return

        import re
        files = []
        for f in os.listdir(package_dir):
            if os.path.isfile(os.path.join(package_dir, f)):
                name_lower = f.lower()
                if name_lower.endswith('.txt'):
                     continue
                if re.match(r'^(image|video)_\d+\.(jpg|jpeg|png|mp4)$', name_lower):
                     files.append(os.path.join(package_dir, f))

        if not files:
            messagebox.showwarning(
                "Không có tệp tin",
                f"Không có ảnh hay video nào trong thư mục của đơn {tracking_number}!"
            )
            return

        hwnd_dialog = self.find_file_dialog()
        if not hwnd_dialog:
            messagebox.showwarning(
                "Hộp thoại chưa mở",
                "Không tìm thấy hộp thoại Chọn Tệp (Open Dialog) của Windows!\n\n"
                "👉 Vui lòng click vào dấu cộng '+' (Bấm tải lên) trên hệ thống JMS trước, sau đó bấm nút này."
            )
            return

        success = self.inject_files_into_dialog(hwnd_dialog, files)
        if success:
             self.show_toast(f"Đã tự động tải lên {len(files)} tệp tin!")
        else:
             messagebox.showerror(
                 "Lỗi tải lên",
                 "Không thể tự động điền file vào hộp thoại.\n"
                 "Hãy chắc chắn hộp thoại Chọn tệp Windows đang mở trên màn hình."
             )

    def find_file_dialog(self):
        dialogs = []
        def enum_windows_callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                class_name = win32gui.GetClassName(hwnd)
                if class_name == "#32770":
                    title = win32gui.GetWindowText(hwnd).lower()
                    if any(x in title for x in ["open", "mở", "chọn", "upload", "select", "tải lên"]):
                        dialogs.append(hwnd)
            return True
        win32gui.EnumWindows(enum_windows_callback, None)
        return dialogs[0] if dialogs else None

    def inject_files_into_dialog(self, hwnd, file_paths):
        edit_hwnd = 0
        def find_edit(h, extra):
            nonlocal edit_hwnd
            c_name = win32gui.GetClassName(h)
            if c_name.lower() == "edit":
                edit_hwnd = h
                return False
            return True

        win32gui.EnumChildWindows(hwnd, find_edit, None)
        if not edit_hwnd:
            edit_hwnd = win32gui.FindWindowEx(hwnd, 0, "Edit", None)
        if not edit_hwnd:
            return False

        formatted_paths = " ".join(f'"{os.path.abspath(p)}"' for p in file_paths)

        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.1)

        win32gui.SendMessage(edit_hwnd, win32con.WM_SETTEXT, 0, formatted_paths)
        time.sleep(0.1)

        btn_hwnd = 0
        def find_button(h, extra):
            nonlocal btn_hwnd
            c_name = win32gui.GetClassName(h)
            if c_name.lower() == "button":
                ctrl_id = win32gui.GetDlgCtrlID(h)
                if ctrl_id == 1:
                     btn_hwnd = h
                     return False
            return True

        win32gui.EnumChildWindows(hwnd, find_button, None)

        if btn_hwnd:
            win32gui.PostMessage(hwnd, win32con.WM_COMMAND, 1, btn_hwnd)
        else:
            win32gui.PostMessage(edit_hwnd, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
            win32gui.PostMessage(edit_hwnd, win32con.WM_KEYUP, win32con.VK_RETURN, 0)

        return True

if __name__ == "__main__":
    root = ctk.CTk()
    app = JMSPopupApp(root)
    root.mainloop()
