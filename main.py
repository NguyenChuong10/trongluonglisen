import os
import sys
import threading
import asyncio
try:
    import tkinter as tk
    import customtkinter as ctk
    HAS_TK = True
except ImportError:
    HAS_TK = False

# Adjust paths to import server and automation correctly
if hasattr(sys, '_MEIPASS'):
    sys.path.append(sys._MEIPASS)
    sys.path.append(os.path.join(sys._MEIPASS, "backend"))
else:
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
import server
try:
    from popup_tool import JMSPopupApp
except ImportError:
    pass # Will be handled by HAS_TK

def run_playwright_loop():
    # Run Playwright loop inside this background thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server.main_loop = loop  # Set the global variable in server.py
    try:
        loop.run_forever()
    except Exception as e:
        print(f"Playwright loop error: {e}")

if __name__ == "__main__":
    import license_verifier

    def start_application():
        # Check if we should only run the Tkinter popup window (standalone mode)
        if "--popup" in sys.argv:
            if HAS_TK:
                root = ctk.CTk()
                app = JMSPopupApp(root)
                
                def on_popup_only_closing():
                    print("Closing standalone popup...")
                    root.destroy()
                    sys.exit(0)
                    
                root.protocol("WM_DELETE_WINDOW", on_popup_only_closing)
                root.mainloop()
            else:
                print("Lỗi: Không tìm thấy Tkinter để mở Popup.")
            sys.exit(0)

        # 1. Start HTTP Server in a background thread
        server_thread = threading.Thread(target=server.start_server, daemon=True)
        server_thread.start()
        
        # 2. Start Playwright loop in a background thread
        playwright_thread = threading.Thread(target=run_playwright_loop, daemon=True)
        playwright_thread.start()
        
        # 3. Start Tkinter in the main GUI thread or wait if headless
        if HAS_TK:
            root = ctk.CTk()
            app = JMSPopupApp(root)
            
            # Clean shutdown on closing Tkinter window
            def on_closing():
                print("Closing application...")
                # Clean up browser context before exiting
                if server.automation:
                    if server.main_loop:
                        try:
                            future = asyncio.run_coroutine_threadsafe(server.automation.close_browser(), server.main_loop)
                            # wait up to 2 seconds for clean stop
                            future.result(timeout=2.0)
                        except Exception:
                            pass
                root.destroy()
                sys.exit(0)
                
            root.protocol("WM_DELETE_WINDOW", on_closing)
            root.mainloop()
        else:
            print("\n" + "="*50)
            print("CHẾ ĐỘ KHÔNG GIAO DIỆN POPUP (Lỗi thiếu thư viện Tkinter)")
            print("Ứng dụng vẫn đang chạy ngầm!")
            print("Vui lòng mở trình duyệt và truy cập: http://localhost:5050")
            print("Nhấn Ctrl+C để tắt ứng dụng.")
            print("="*50 + "\n")
            try:
                import time
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("Closing application...")
                if server.automation:
                    if server.main_loop:
                        try:
                            future = asyncio.run_coroutine_threadsafe(server.automation.close_browser(), server.main_loop)
                            future.result(timeout=2.0)
                        except Exception:
                            pass
                sys.exit(0)

    # Force license validation before starting application
    license_verifier.verify_and_enforce_license(start_application)
