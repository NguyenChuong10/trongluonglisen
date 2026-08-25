import os
import sys
import uuid
import hmac
import hashlib
import winreg
import time
from datetime import datetime
import customtkinter as ctk
import tkinter as tk

SECRET_SALT = "JMS_Helper_Secret_Key_2026_@!"

# Setup pathing
if hasattr(sys, '_MEIPASS'):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DATA_DIR = os.path.join(BASE_DIR, "data")
LICENSE_FILE = os.path.join(DATA_DIR, "license.key")

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
    # Trước tiên kiểm tra xem có hack thời gian không
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

class ActivationDialog(ctk.CTk):
    def __init__(self, on_success_callback=None):
        super().__init__()
        self.on_success_callback = on_success_callback
        self.activated = False
        
        self.title("Kích hoạt bản quyền - JMS Helper")
        self.geometry("520x360")
        self.resizable(False, False)
        
        # Luôn hiển thị trên cùng để người dùng không bỏ qua
        self.attributes("-topmost", True)
        
        # Giao diện tối
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.setup_ui()
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def setup_ui(self):
        # Frame chính
        main_frame = ctk.CTkFrame(self, fg_color="#1e293b") # Slate 800
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Tiêu đề
        title_label = ctk.CTkLabel(
            main_frame, 
            text="JMS HELPER - KÍCH HOẠT BẢN QUYỀN", 
            font=("Segoe UI", 16, "bold"), 
            text_color="#ef4444" # Đỏ J&T
        )
        title_label.pack(pady=(15, 5))
        
        sub_label = ctk.CTkLabel(
            main_frame,
            text="Vui lòng gửi Mã thiết bị sau cho Admin để nhận mã kích hoạt.",
            font=("Segoe UI", 11),
            text_color="#94a3b8" # Slate 400
        )
        sub_label.pack(pady=(0, 15))
        
        # Frame hiển thị Machine ID
        mid_frame = ctk.CTkFrame(main_frame, fg_color="#0f172a", height=50) # Slate 900
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
        
        # Ô nhập key
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
        
        # Label thông báo lỗi/thành công
        self.status_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=("Segoe UI", 11, "bold"),
            text_color="#ef4444"
        )
        self.status_label.pack(pady=5)
        
        # Nút Kích hoạt & Thoát
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
        
        # Hiển thị thông báo tạm thời
        old_status = self.status_label.cget("text")
        old_color = self.status_label.cget("text_color")
        self.status_label.configure(text="Đã sao chép mã thiết bị vào bộ nhớ đệm!", text_color="#10b981")
        self.after(2000, lambda: self.status_label.configure(text=old_status, text_color=old_color))
        
    def check_activation(self):
        key = self.key_textbox.get("1.0", "end-1c").strip()
        is_valid, msg = verify_license_key(key)
        
        if is_valid:
            self.status_label.configure(text=msg, text_color="#10b981")
            # Tạo thư mục data nếu chưa có
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(LICENSE_FILE, "w", encoding="utf-8") as f:
                f.write(key)
            self.activated = True
            
            # Đóng cửa sổ và chạy callback tiếp tục ứng dụng
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
    """Hộp thoại kích hoạt cho môi trường không có giao diện Tkinter."""
    print("\n" + "="*60)
    print("ỨNG DỤNG CHƯA ĐƯỢC KÍCH HOẠT HOẶC ĐÃ HẾT HẠN BẢN QUYỀN")
    print("="*60)
    print(f"Mã thiết bị của bạn: {get_machine_id()}")
    print("Vui lòng sao chép mã trên gửi cho Admin để nhận khóa kích hoạt.")
    print("="*60 + "\n")
    
    # Kiểm tra xem có chỉnh sửa ngày hệ thống không
    if check_time_tampering():
        print("[Lỗi] Phát hiện thời gian hệ thống không chính xác (nghi vấn lùi giờ).")
        print("Vui lòng chỉnh lại giờ hệ thống đúng chuẩn và mở lại ứng dụng.")
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

def verify_and_enforce_license(on_success):
    """
    Hàm gọi từ main.py để bắt buộc check bản quyền.
    Nếu hợp lệ thì chạy tiếp hàm on_success.
    Nếu không hợp lệ thì mở giao diện kích hoạt hoặc CLI kích hoạt.
    """
    # 1. Phát hiện gian lận thời gian hệ thống trước
    if check_time_tampering():
        msg = "Phát hiện thời gian hệ thống bị lùi ngược! Vui lòng đồng bộ lại giờ chuẩn."
        print(f"\n[LỖI BẢN QUYỀN] {msg}\n")
        # Nếu có giao diện CTk, hiện cảnh báo và tắt
        try:
            root = ctk.CTk()
            root.withdraw()
            # Dùng tkinter chuẩn để báo lỗi nếu CTk lỗi
            from tkinter import messagebox
            messagebox.showerror("Lỗi bản quyền", msg)
            root.destroy()
        except Exception:
            pass
        sys.exit(0)
        
    # 2. Kiểm tra key đã lưu sẵn
    if check_license_saved():
        on_success()
    else:
        # Nếu chưa kích hoạt, mở hộp thoại
        try:
            dialog = ActivationDialog(on_success_callback=on_success)
            dialog.mainloop()
        except Exception as e:
            # Fallback về CLI nếu môi trường không cho phép mở cửa sổ (headless)
            prompt_activation_cli()
