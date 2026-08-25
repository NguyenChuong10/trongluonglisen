import os
import sys
import hmac
import hashlib
from datetime import datetime, timedelta

SECRET_SALT = "JMS_Helper_Secret_Key_2026_@!"

def get_clean_input(prompt):
    try:
        return input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\nĐã thoát chương trình.")
        sys.exit(0)

def main():
    print("=" * 60)
    print("      JMS HELPER - CÔNG CỤ TẠO MÃ KÍCH HOẠT (ADMIN)      ")
    print("=" * 60)
    
    # 1. Nhập Machine ID
    machine_id = ""
    while not machine_id:
        machine_id = get_clean_input("1. Nhập Mã thiết bị (Machine ID) của khách: ").upper()
        if not machine_id:
            print("Mã thiết bị không được để trống!")
            
    # 2. Chọn/Nhập thời hạn
    print("\n2. Chọn thời hạn sử dụng bản quyền:")
    print("   [1] 1 tháng (30 ngày)")
    print("   [2] 3 tháng (90 ngày)")
    print("   [3] 6 tháng (180 ngày)")
    print("   [4] 1 năm (365 ngày)")
    print("   [5] Nhập ngày cụ thể (Định dạng YYYYMMDD - Ví dụ: 20261231)")
    
    choice = ""
    while choice not in ["1", "2", "3", "4", "5"]:
        choice = get_clean_input("Nhập lựa chọn của bạn (1-5): ")
        
    expiry_date = None
    today = datetime.now().date()
    
    if choice == "1":
        expiry_date = today + timedelta(days=30)
    elif choice == "2":
        expiry_date = today + timedelta(days=90)
    elif choice == "3":
        expiry_date = today + timedelta(days=180)
    elif choice == "4":
        expiry_date = today + timedelta(days=365)
    elif choice == "5":
        while not expiry_date:
            date_str = get_clean_input("Nhập ngày hết hạn (YYYYMMDD): ")
            try:
                expiry_date = datetime.strptime(date_str, "%Y%m%d").date()
                if expiry_date < today:
                    print("Cảnh báo: Ngày hết hạn đã ở quá khứ!")
            except ValueError:
                print("Lỗi: Định dạng ngày không hợp lệ. Vui lòng nhập lại (ví dụ 20261231).")
                
    expiry_str = expiry_date.strftime("%Y%m%d")
    
    # 3. Tạo Signature
    msg = f"{machine_id}|{expiry_str}"
    sig = hmac.new(SECRET_SALT.encode(), msg.encode(), hashlib.sha256).hexdigest()[:16].upper()
    
    # 4. Xuất mã kích hoạt
    license_key = f"{machine_id}-{expiry_str}-{sig}"
    
    print("\n" + "=" * 60)
    print("THÔNG TIN BẢN QUYỀN TẠO MỚI:")
    print(f"- Mã thiết bị: {machine_id}")
    print(f"- Ngày hết hạn: {expiry_date.strftime('%d/%m/%Y')} (Hết hạn sau {(expiry_date - today).days} ngày)")
    print(f"- Mã kích hoạt (License Key):")
    print("\n" + license_key + "\n")
    print("=" * 60)
    
    # Cố gắng tự động copy vào clipboard để bạn gửi cho khách nhanh hơn
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(license_key)
        root.update()
        root.destroy()
        print("[Thông báo] Đã tự động sao chép Mã kích hoạt vào bộ nhớ đệm (Clipboard)!")
    except Exception:
        pass
        
    print("\nVui lòng copy dòng License Key ở trên để gửi cho khách hàng.")
    get_clean_input("\nNhấn Enter để đóng...")

if __name__ == "__main__":
    main()
