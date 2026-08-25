import os
import sys
import uuid
import hmac
import hashlib
import winreg
import time
import base64
from datetime import datetime

SECRET_SALT = "JMS_Helper_Secret_Key_2026_@!"
REG_PATH = r"Software\JMS_Helper"
REG_KEY = "TrialStart"

# Setup pathing
if hasattr(sys, '_MEIPASS'):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DATA_DIR = os.path.join(BASE_DIR, "data")
LICENSE_FILE = os.path.join(DATA_DIR, "license.key")
TRIAL_FILE = os.path.join(DATA_DIR, "trial.dat")

# Setup Tkinter components dynamically
import customtkinter as ctk
import tkinter as tk

def get_machine_id():
    """Lấy mã định danh phần cứng duy nhất của máy tính chạy Windows."""
    try:
        # Sử dụng MachineGuid của Windows registry (cực kỳ độc nhất và ổn định)
        registry_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        value, regtype = winreg.QueryValueEx(registry_key, "MachineGuid")
        winreg.CloseKey(registry_key)
        return str(value).strip().upper()
    except Exception:
        # Fallback sang địa chỉ MAC nếu lỗi
        node = uuid.getnode()
        return f"MAC-{node:012X}"

def generate_key_signature(machine_id, expiry_str):
    """Tạo signature bảo mật HMAC-SHA256 từ MachineID và Expiry Date."""
    msg = f"{machine_id}|{expiry_str}"
    return hmac.new(SECRET_SALT.encode(), msg.encode(), hashlib.sha256).hexdigest()[:16].upper()

def verify_license_key(key):
    """
    Xác minh mã kích hoạt xem có hợp lệ và còn hạn hay không.
    Định dạng key: <MACHINE_ID>-<YYYYMMDD>-<SIGNATURE>
    """
    if not key:
        return False, "Vui lòng nhập mã kích hoạt."
    
    parts = key.strip().upper().split('-')
    if len(parts) < 3:
        return False, "Định dạng mã kích hoạt không hợp lệ."
        
    signature = parts[-1]
    expiry_str = parts[-2]
    machine_id = "-".join(parts[:-2])
    
    # 1. Kiểm tra Machine ID
    curr_machine_id = get_machine_id()
    if machine_id != curr_machine_id:
        return False, "Mã kích hoạt không dành cho máy tính này."
        
    # 2. Kiểm tra chữ ký bảo mật
    expected_sig = generate_key_signature(machine_id, expiry_str)
    if signature != expected_sig:
        return False, "Mã kích hoạt không hợp lệ."
        
    # 3. Kiểm tra ngày hết hạn
    try:
        expiry_date = datetime.strptime(expiry_str, "%Y%m%d").date()
    except ValueError:
        return False, "Định dạng ngày hết hạn trong mã không hợp lệ."
        
    if datetime.now().date() > expiry_date:
        return False, f"Mã kích hoạt đã hết hạn vào ngày {expiry_date.strftime('%d/%m/%Y')}."
        
    return True, f"Hợp lệ đến ngày {expiry_date.strftime('%d/%m/%Y')}."

def check_time_tampering():
    """Kiểm tra xem người dùng có lùi ngày hệ thống để lách luật không."""
    files_to_check = [
        os.path.join(DATA_DIR, "backend.log"),
        os.path.join(DATA_DIR, "scanned_packages.json"),
        os.path.join(BASE_DIR, "settings.json")
    ]
    current_time = time.time()
    for file_path in files_to_check:
        if os.path.exists(file_path):
            try:
                mtime = os.path.getmtime(file_path)
                # Nếu thời gian hệ thống hiện tại nhỏ hơn thời gian chỉnh sửa file cuối cùng quá 1 giờ
                if current_time < (mtime - 3600):
                    return True
            except Exception:
                pass
    return False

def check_license_saved():
    """Kiểm tra key đã lưu sẵn trong file."""
    if check_time_tampering():
        return False
        
    if not os.path.exists(LICENSE_FILE):
        return False
    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            key = f.read().strip()
        is_valid, _ = verify_license_key(key)
        return is_valid
    except Exception:
        return False

# ==========================================
# CÁC HÀM XỬ LÝ HẠN DÙNG THỬ (AUTO-TRIAL)
# ==========================================

def get_registry_trial_date():
    """Đọc ngày bắt đầu dùng thử từ Windows Registry."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, REG_KEY)
        winreg.CloseKey(key)
        decoded = base64.b64decode(value.encode()).decode()
        return datetime.strptime(decoded, "%Y%m%d").date()
    except Exception:
        return None

def set_registry_trial_date(date_val):
    """Ghi ngày bắt đầu dùng thử vào Windows Registry."""
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
        encoded = base64.b64encode(date_val.strftime("%Y%m%d").encode()).decode()
        winreg.SetValueEx(key, REG_KEY, 0, winreg.REG_SZ, encoded)
        winreg.CloseKey(key)
    except Exception:
        pass

def get_file_trial_date():
    """Đọc ngày bắt đầu dùng thử từ file trial.dat trong thư mục data."""
    if not os.path.exists(TRIAL_FILE):
        return None
    try:
        with open(TRIAL_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        decoded = base64.b64decode(content.encode()).decode()
        return datetime.strptime(decoded, "%Y%m%d").date()
    except Exception:
        return None

def set_file_trial_date(date_val):
    """Ghi ngày bắt đầu dùng thử vào file trial.dat."""
    try:
        os.makedirs(os.path.dirname(TRIAL_FILE), exist_ok=True)
        encoded = base64.b64encode(date_val.strftime("%Y%m%d").encode()).decode()
        with open(TRIAL_FILE, "w", encoding="utf-8") as f:
            f.write(encoded)
    except Exception:
        pass

def check_trial_status():
    """
    Kiểm tra trạng thái dùng thử 30 ngày.
    Trả về (is_in_trial, remaining_days, message)
    """
    if check_time_tampering():
        return False, 0, "Phát hiện thời gian hệ thống không chính xác (nghi vấn lùi giờ)."

    reg_date = get_registry_trial_date()
    file_date = get_file_trial_date()

    if not reg_date and not file_date:
        # Lần đầu tiên chạy app: Tạo ngày bắt đầu dùng thử là hôm nay
        today = datetime.now().date()
        set_registry_trial_date(today)
        set_file_trial_date(today)
        return True, 30, "Bắt đầu dùng thử 30 ngày."

    # Đồng bộ hóa ngày nếu một trong hai bên bị xóa/tamper
    if reg_date and not file_date:
        set_file_trial_date(reg_date)
        start_date = reg_date
    elif file_date and not reg_date:
        set_registry_trial_date(file_date)
        start_date = file_date
    else:
        # Nếu cả 2 đều tồn tại, lấy ngày cũ nhất để tránh reset
        start_date = min(reg_date, file_date)
        set_registry_trial_date(start_date)
        set_file_trial_date(start_date)

    today = datetime.now().date()
    elapsed = (today - start_date).days

    if elapsed < 0:
        return False, 0, "Thời gian hệ thống không khớp với ngày bắt đầu dùng thử."

    remaining = 30 - elapsed
    if remaining >= 0:
        return True, remaining, f"Hạn dùng thử còn lại: {remaining} ngày."
    else:
        return False, 0, "Đã hết thời hạn dùng thử 30 ngày."

# ==========================================
# GIAO DIỆN KÍCH HOẠT (CUSTOMTKINTER)
# ==========================================

class ActivationDialog(ctk.CTk):
    def __init__(self, on_success_callback=None):
        super().__init__()
        self.on_success_callback = on_success_callback
        self.activated = False
        
        self.title("Kích hoạt bản quyền - JMS Helper")
        self.geometry("520x360")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.setup_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def setup_ui(self):
        main_frame = ctk.CTkFrame(self, fg_color="#1e293b")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        title_label = ctk.CTkLabel(
            main_frame, 
            text="JMS HELPER - ĐĂNG KÝ BẢN QUYỀN", 
            font=("Segoe UI", 16, "bold"), 
            text_color="#ef4444"
        )
        title_label.pack(pady=(15, 5))
        
        sub_label = ctk.CTkLabel(
            main_frame,
            text="Phần mềm chưa được kích hoạt hoặc đã hết 30 ngày dùng thử.",
            font=("Segoe UI", 11),
            text_color="#94a3b8"
        )
        sub_label.pack(pady=(0, 15))
        
        mid_frame = ctk.CTkFrame(main_frame, fg_color="#0f172a", height=50)
        mid_frame.pack(fill="x", padx=20, pady=5)
        
        machine_id = get_machine_id()
        
        self.id_entry = ctk.CTkEntry(
            mid_frame, 
            width=320, 
            fg_color="transparent", 
            border_width=0, 
            font=("Consolas", 11), 
            text_color="#f8fafc"
        )
        self.id_entry.insert(0, machine_id)
        self.id_entry.configure(state="readonly")
        self.id_entry.pack(side="left", padx=10, pady=10)
        
        copy_btn = ctk.CTkButton(
            mid_frame,
            text="Sao chép",
            width=70,
            fg_color="#3b82f6",
            hover_color="#2563eb",
            font=("Segoe UI", 10, "bold"),
            command=self.copy_id
        )
        copy_btn.pack(side="right", padx=10, pady=10)
        
        key_label = ctk.CTkLabel(
            main_frame,
            text="Nhập mã kích hoạt (License Key):",
            font=("Segoe UI", 11, "bold"),
            text_color="#f8fafc"
        )
        key_label.pack(anchor="w", padx=20, pady=(15, 2))
        
        self.key_textbox = ctk.CTkTextbox(
            main_frame,
            height=60,
            font=("Consolas", 10),
            fg_color="#0f172a",
            border_color="#334155",
            border_width=1
        )
        self.key_textbox.pack(fill="x", padx=20, pady=5)
        
        self.status_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=("Segoe UI", 11, "bold"),
            text_color="#ef4444"
        )
        self.status_label.pack(pady=5)
        
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(pady=(5, 10))
        
        activate_btn = ctk.CTkButton(
            btn_frame,
            text="KÍCH HOẠT",
            width=140,
            height=35,
            fg_color="#ef4444",
            hover_color="#dc2626",
            font=("Segoe UI", 12, "bold"),
            command=self.check_activation
        )
        activate_btn.pack(side="left", padx=10)
        
        exit_btn = ctk.CTkButton(
            btn_frame,
            text="THOÁT",
            width=100,
            height=35,
            fg_color="#475569",
            hover_color="#334155",
            font=("Segoe UI", 12, "bold"),
            command=self.on_close
        )
        exit_btn.pack(side="right", padx=10)
        
    def copy_id(self):
        self.clipboard_clear()
        self.clipboard_append(self.id_entry.get())
        self.update()
        
        old_status = self.status_label.cget("text")
        old_color = self.status_label.cget("text_color")
        self.status_label.configure(text="Đã sao chép mã thiết bị vào bộ nhớ đệm!", text_color="#10b981")
        self.after(2000, lambda: self.status_label.configure(text=old_status, text_color=old_color))
        
    def check_activation(self):
        key = self.key_textbox.get("1.0", "end-1c").strip()
        is_valid, msg = verify_license_key(key)
        
        if is_valid:
            self.status_label.configure(text=msg, text_color="#10b981")
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(LICENSE_FILE, "w", encoding="utf-8") as f:
                f.write(key)
            self.activated = True
            self.after(1500, self.success_exit)
        else:
            self.status_label.configure(text=msg, text_color="#ef4444")
            
    def success_exit(self):
        self.destroy()
        if self.on_success_callback:
            self.on_success_callback()
            
    def on_close(self):
        self.destroy()
        sys.exit(0)

def prompt_activation_cli():
    """Hộp thoại kích hoạt cho môi trường CLI (không hỗ trợ GUI)."""
    print("\n" + "="*60)
    print("ỨNG DỤNG CHƯA ĐƯỢC KÍCH HOẠT HOẶC ĐÃ HẾT HẠN DÙNG THỬ 30 NGÀY")
    print("="*60)
    print(f"Mã thiết bị của bạn: {get_machine_id()}")
    print("Vui lòng gửi mã trên cho Admin để nhận khóa kích hoạt.")
    print("="*60 + "\n")
    
    if check_time_tampering():
        print("[Lỗi] Phát hiện thời gian hệ thống không chính xác (nghi vấn lùi giờ).")
        sys.exit(0)
        
    try:
        key = input("Nhập mã kích hoạt (License Key) tại đây: ").strip()
        is_valid, msg = verify_license_key(key)
        if is_valid:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(LICENSE_FILE, "w", encoding="utf-8") as f:
                f.write(key)
            print(f"\n[Thành công] {msg}\nKhởi chạy ứng dụng...")
        else:
            print(f"\n[Lỗi] {msg}")
            sys.exit(0)
    except KeyboardInterrupt:
        print("\nĐã hủy kích hoạt.")
        sys.exit(0)

# ==========================================
# HÀM ĐIỀU PHỐI CHÍNH (ĐƯỢC GỌI TỪ MAIN.PY)
# ==========================================

def verify_and_enforce_license(on_success):
    """
    Hàm gọi từ main.py để kiểm soát quyền khởi chạy ứng dụng.
    Kiểm tra lần lượt: Chống lùi giờ -> Key lưu sẵn -> Hạn dùng thử.
    """
    # 1. Phát hiện lùi giờ hệ thống
    if check_time_tampering():
        msg = "Phát hiện thời gian hệ thống bị lùi ngược! Vui lòng đồng bộ lại giờ chuẩn."
        print(f"\n[LỖI BẢN QUYỀN] {msg}\n")
        try:
            root = ctk.CTk()
            root.withdraw()
            from tkinter import messagebox
            messagebox.showerror("Lỗi bản quyền", msg)
            root.destroy()
        except Exception:
            pass
        sys.exit(0)
        
    # 2. Kiểm tra nếu đã kích hoạt Key bản quyền thành công trước đó
    if check_license_saved():
        print("[Bản quyền] Đã kích hoạt bản quyền chính thức.")
        on_success()
        return

    # 3. Nếu chưa kích hoạt Key, kiểm tra xem còn trong hạn dùng thử 30 ngày hay không
    is_in_trial, remaining_days, trial_msg = check_trial_status()
    if is_in_trial:
        print(f"[Dùng thử] {trial_msg}")
        on_success()
        return

    # 4. Hết hạn dùng thử và chưa kích hoạt -> Bắt buộc mở bảng kích hoạt
    print(f"[Yêu cầu kích hoạt] {trial_msg}")
    try:
        dialog = ActivationDialog(on_success_callback=on_success)
        dialog.mainloop()
    except Exception as e:
        prompt_activation_cli()
