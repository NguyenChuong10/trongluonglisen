import os
from filelock import FileLock
import json
import asyncio
import threading
import sys
import webbrowser
import base64

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Redirect stdout/stderr to a log file for debugging
try:
    os.makedirs("data", exist_ok=True)
    log_file = open("data/backend.log", "a", encoding="utf-8")
    class Tee:
        def __init__(self, *files):
            self.files = files
        def write(self, obj):
            for f in self.files:
                f.write(obj)
                f.flush()
        def flush(self):
            for f in self.files:
                f.flush()
    sys.stdout = Tee(sys.stdout, log_file)
    sys.stderr = Tee(sys.stderr, log_file)
    print("\n--- BACKEND START ---")
except Exception as le:
    print(f"Error setting up logger: {le}")
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote
from automation import JMSAutomation

# Paths
if hasattr(sys, '_MEIPASS'):
    FRONTEND_DIR = os.path.join(sys._MEIPASS, "frontend")
    DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(sys.executable), "data"))
    SETTINGS_FILE = os.path.abspath(os.path.join(os.path.dirname(sys.executable), "settings.json"))
else:
    FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
    DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    SETTINGS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "settings.json"))

# Global automation instance and event loop
automation = JMSAutomation()
main_loop = None

def run_async(coro):
    """Utility to run an async coroutine on the main loop from another thread."""
    future = asyncio.run_coroutine_threadsafe(coro, main_loop)
    return future.result()

class JMSHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # We override directory to point to frontend folder
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def end_headers(self):
        # Disable caching for all files to ensure instant updates of UI changes
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        if self.path.startswith('/api/'):
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # Serve data files (images and videos) for UI preview
        if path.startswith("/data/"):
            relative_path = path[6:] # remove "/data/"
            # Avoid path traversal attacks
            relative_path = unquote(relative_path).replace("\\", "/")
            filepath = os.path.abspath(os.path.join(DATA_DIR, relative_path))
            
            # Secure path check using commonpath
            if filepath.startswith(DATA_DIR) and os.path.exists(filepath) and os.path.isfile(filepath):
                if os.path.commonpath([DATA_DIR]) == os.path.commonpath([DATA_DIR, filepath]):
                    self.send_response(200)
                    import mimetypes
                    ctype, _ = mimetypes.guess_type(filepath)
                    self.send_header('Content-Type', ctype or 'application/octet-stream')
                    self.end_headers()
                    with open(filepath, 'rb') as f:
                        self.wfile.write(f.read())
                else:
                    self.send_response(404)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()
            return

        # Handle REST APIs
        if path == "/api/status":
            try:
                status = run_async(automation.get_status())
                self.send_json_response(200, status)
            except Exception as e:
                self.send_json_response(500, {"error": str(e)})
                
        elif path == "/api/screenshot":
            try:
                if automation.zalo_page:
                    # Capture screenshot of the active Zalo page
                    img_path = os.path.join(DATA_DIR, "zalo_current.png")
                    run_async(automation.zalo_page.screenshot(path=img_path))
                    self.send_json_response(200, {"status": "success", "message": "Screenshot saved"})
                else:
                    self.send_json_response(400, {"status": "error", "message": "zalo_page not initialized"})
            except Exception as e:
                self.send_json_response(500, {"status": "error", "message": str(e)})
                
        elif path == "/api/settings":
            self.handle_get_settings()
            
        elif path == "/api/packages":
            self.handle_get_packages()
            
        else:
            # Fallback to serving static files from FRONTEND_DIR
            super().do_GET()

    def do_POST(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b''
        
        try:
            body = json.loads(post_data.decode('utf-8')) if post_data else {}
        except Exception:
            body = {}

        if path == "/api/start-browser":
            try:
                run_async(automation.start_browser())
                self.send_json_response(200, {"status": "success", "message": "Browser started successfully"})
            except Exception as e:
                self.send_json_response(500, {"status": "error", "message": str(e)})

        elif path == "/api/eval":
            try:
                script = body.get("script")
                if automation.zalo_page:
                    res = run_async(automation.zalo_page.evaluate(script))
                    self.send_json_response(200, {"status": "success", "result": res})
                else:
                    self.send_json_response(400, {"status": "error", "message": "zalo_page not initialized"})
            except Exception as e:
                self.send_json_response(500, {"status": "error", "message": str(e)})

        elif path == "/api/press-key":
            try:
                key = body.get("key", "Control+f")
                if automation.zalo_page:
                    run_async(automation.zalo_page.keyboard.press(key))
                    self.send_json_response(200, {"status": "success", "message": f"Pressed key {key}"})
                else:
                    self.send_json_response(400, {"status": "error", "message": "zalo_page not initialized"})
            except Exception as e:
                self.send_json_response(500, {"status": "error", "message": str(e)})

        elif path == "/api/close-browser":
            try:
                run_async(automation.close_browser())
                self.send_json_response(200, {"status": "success", "message": "Browser closed successfully"})
            except Exception as e:
                self.send_json_response(500, {"status": "error", "message": str(e)})

        elif path == "/api/open-folder":
            try:
                os.startfile(DATA_DIR)
                self.send_json_response(200, {"status": "success", "message": "Folder opened successfully"})
            except Exception as e:
                self.send_json_response(500, {"status": "error", "message": str(e)})

        elif path == "/api/scroll-zalo":
            times = body.get("times", 15)
            try:
                run_async(automation.scroll_zalo(times))
                self.send_json_response(200, {"status": "success", "message": f"Scrolled Zalo chat {times} times"})
            except Exception as e:
                self.send_json_response(500, {"status": "error", "message": str(e)})

        elif path == "/api/stop-scan":
            automation.stop_requested = True
            automation.current_action_progress = "Đang dừng quét..."
            self.send_json_response(200, {"status": "success", "message": "Yêu cầu dừng quét đã được gửi."})

        elif path == "/api/scan-download-5in1":
            try:
                direction = body.get("direction", "up")
                start_tracking = body.get("startTracking", None)
                automation.current_action_progress = f"Khởi động quét & tải tự động (5-in-1, hướng: {direction}, mốc: {start_tracking})..."
                async def progress_callback(msg):
                    automation.current_action_progress = msg
                from action_5in1 import run_5in1
                packages = run_async(run_5in1(automation, progress_callback, direction=direction, start_tracking=start_tracking))
                automation.current_action_progress = "Hoàn thành"
                self.send_json_response(200, {"status": "success", "packages": packages})
            except Exception as e:
                automation.current_action_progress = f"Lỗi: {str(e)}"
                self.send_json_response(500, {"status": "error", "message": str(e)})

        elif path == "/api/scan-th1":
            try:
                start_tracking = body.get("startTracking", None)
                automation.current_action_progress = f"Khởi động quét mốc xuôi TH1 (mốc: {start_tracking})..."
                async def progress_callback(msg):
                    automation.current_action_progress = msg
                from action_th1 import run_th1
                packages = run_async(run_th1(automation, progress_callback, start_tracking=start_tracking))
                automation.current_action_progress = "Hoàn thành"
                self.send_json_response(200, {"status": "success", "packages": packages})
            except Exception as e:
                automation.current_action_progress = f"Lỗi: {str(e)}"
                self.send_json_response(500, {"status": "error", "message": str(e)})

        elif path == "/api/scan-th2":
            try:
                start_tracking = body.get("startTracking", None)
                automation.current_action_progress = f"Khởi động quét mốc ngược TH2 (mốc: {start_tracking})..."
                async def progress_callback(msg):
                    automation.current_action_progress = msg
                from action_th2 import run_th2
                packages = run_async(run_th2(automation, progress_callback, start_tracking=start_tracking))
                automation.current_action_progress = "Hoàn thành"
                self.send_json_response(200, {"status": "success", "packages": packages})
            except Exception as e:
                automation.current_action_progress = f"Lỗi: {str(e)}"
                self.send_json_response(500, {"status": "error", "message": str(e)})

        elif path == "/api/scan-zalo":
            try:
                direction = body.get("direction", "down")
                start_tracking = body.get("startTracking", None)
                packages = run_async(automation.scan_zalo(direction=direction, start_tracking=start_tracking))
                
                # Load previous packages to preserve status and folder names
                scanned_path = os.path.join(DATA_DIR, "scanned_packages.json")
                old_packages = []
                if os.path.exists(scanned_path):
                    with FileLock(scanned_path + '.lock', timeout=5), open(scanned_path, "r", encoding="utf-8") as f:
                        try:
                            old_packages = json.load(f)
                        except Exception:
                            old_packages = []
                            
                old_map = {p["trackingNumber"]: p for p in old_packages if "trackingNumber" in p}
                
                # Scan DATA_DIR to find the absolute max folder index currently on disk
                max_folder_idx = 0
                if os.path.exists(DATA_DIR):
                    for item in os.listdir(DATA_DIR):
                        if os.path.isdir(os.path.join(DATA_DIR, item)):
                            try:
                                val = int(item)
                                if val > max_folder_idx:
                                    max_folder_idx = val
                            except ValueError:
                                pass
                                
                # Assign folder names and restore statuses
                for pkg in packages:
                    trk = pkg["trackingNumber"]
                    
                    # 1. First, check if this tracking number is in old_packages
                    old_folder = None
                    if trk in old_map:
                        old_folder = old_map[trk].get("folderName")
                        
                    # Safety check: does old_folder contain another package's txt file?
                    is_folder_clean = True
                    if old_folder:
                        folder_path = os.path.join(DATA_DIR, old_folder)
                        if os.path.exists(folder_path) and os.path.isdir(folder_path):
                            for f_item in os.listdir(folder_path):
                                if f_item.lower().endswith(".txt") and f_item != f"{trk}.txt":
                                    is_folder_clean = False
                                    break
                                    
                    if old_folder and is_folder_clean:
                        old_pkg = old_map[trk]
                        pkg["folderName"] = old_folder
                        pkg["localStatus"] = old_pkg.get("localStatus", "Chưa tải về")
                        pkg["jmsStatus"] = old_pkg.get("jmsStatus", "Chưa xử lý")
                        pkg["images"] = old_pkg.get("images", pkg.get("images", []))
                        pkg["videos"] = old_pkg.get("videos", pkg.get("videos", []))
                        pkg["copied"] = old_pkg.get("copied", False)
                    else:
                        # 2. Otherwise, check if a clean folder with {trk}.txt already exists on disk
                        existing_folder = None
                        if os.path.exists(DATA_DIR):
                            for item in os.listdir(DATA_DIR):
                                item_path = os.path.join(DATA_DIR, item)
                                if os.path.isdir(item_path):
                                    if os.path.exists(os.path.join(item_path, f"{trk}.txt")):
                                        # Check if it has other txt files
                                        has_other = False
                                        for f_item in os.listdir(item_path):
                                            if f_item.lower().endswith(".txt") and f_item != f"{trk}.txt":
                                                has_other = True
                                                break
                                        if not has_other:
                                            existing_folder = item
                                            break
                                        
                        if existing_folder:
                            pkg["folderName"] = existing_folder
                            pkg["localStatus"] = "Đã tải về"
                            pkg["jmsStatus"] = "Chưa xử lý"
                            # Reconstruct local paths for images/videos in this folder
                            folder_path = os.path.join(DATA_DIR, existing_folder)
                            files_in_folder = os.listdir(folder_path)
                            pkg["images"] = [f"/data/{existing_folder}/{f}" for f in files_in_folder if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))]
                            pkg["videos"] = [f"/data/{existing_folder}/{f}" for f in files_in_folder if f.lower().endswith(('.mp4', '.mov', '.avi'))]
                        else:
                            # 3. Assign a brand new folder index
                            max_folder_idx += 1
                            pkg["folderName"] = str(max_folder_idx)
                            pkg["localStatus"] = "Chưa tải về"
                            pkg["jmsStatus"] = "Chưa xử lý"
                            
                # Save scanned list to a local JSON file to persist state
                with FileLock(scanned_path + '.lock', timeout=5), open(scanned_path, "w", encoding="utf-8") as f:
                    json.dump(packages, f, ensure_ascii=False, indent=4)
                self.send_json_response(200, {"status": "success", "packages": packages})
            except Exception as e:
                self.send_json_response(500, {"status": "error", "message": str(e)})

        elif path == "/api/download-package":
            tracking_number = body.get("trackingNumber")
            if not tracking_number:
                self.send_json_response(400, {"status": "error", "message": "Missing trackingNumber"})
                return
                
            try:
                # Find package details in saved scanned list
                scanned_path = os.path.join(DATA_DIR, "scanned_packages.json")
                if not os.path.exists(scanned_path):
                    self.send_json_response(404, {"status": "error", "message": "No scanned packages list found. Scan first!"})
                    return
                    
                with FileLock(scanned_path + '.lock', timeout=5), open(scanned_path, "r", encoding="utf-8") as f:
                    packages = json.load(f)
                    
                package = next((p for p in packages if p["trackingNumber"] == tracking_number), None)
                if not package:
                    self.send_json_response(404, {"status": "error", "message": f"Package {tracking_number} not found in scans"})
                    return

                folder_name = package.get("folderName")
                
                # Safety check: does folder_name contain another package's txt file?
                is_folder_clean = True
                if folder_name:
                    folder_path = os.path.join(DATA_DIR, folder_name)
                    if os.path.exists(folder_path) and os.path.isdir(folder_path):
                        for f_item in os.listdir(folder_path):
                            if f_item.lower().endswith(".txt") and f_item != f"{tracking_number}.txt":
                                is_folder_clean = False
                                break
                                
                if not folder_name or not is_folder_clean:
                    # Scan DATA_DIR to find the absolute max folder index currently on disk
                    max_folder_idx = 0
                    if os.path.exists(DATA_DIR):
                        for item in os.listdir(DATA_DIR):
                            if os.path.isdir(os.path.join(DATA_DIR, item)):
                                try:
                                    val = int(item)
                                    if val > max_folder_idx:
                                        max_folder_idx = val
                                except ValueError:
                                    pass
                    folder_name = str(max_folder_idx + 1)
                    package["folderName"] = folder_name

                # Download media
                imgs, vids = run_async(automation.download_package_media(package, pkg_index=folder_name))
                
                # Update package paths in scanned_packages.json to local served paths
                local_images = [f"/data/{folder_name}/{os.path.basename(img)}" for img in imgs]
                local_videos = [f"/data/{folder_name}/{os.path.basename(vid)}" for vid in vids]
                
                package["images"] = local_images
                package["videos"] = local_videos
                if len(imgs) >= 1 and len(vids) >= 1:
                    package["localStatus"] = "Đã tải về"
                else:
                    package["localStatus"] = f"Lỗi: Có {len(imgs)} ảnh, {len(vids)} video (Cần tối thiểu 1 ảnh & 1 video)"
                
                with FileLock(scanned_path + '.lock', timeout=5), open(scanned_path, "w", encoding="utf-8") as f:
                    json.dump(packages, f, ensure_ascii=False, indent=4)
                
                self.send_json_response(200, {
                    "status": "success", 
                    "message": f"Downloaded {len(imgs)} images and {len(vids)} videos",
                    "images": local_images,
                    "videos": local_videos
                })
            except Exception as e:
                self.send_json_response(500, {"status": "error", "message": str(e)})

        elif path == "/api/upload-jms":
            tracking_number = body.get("trackingNumber")
            weight = body.get("weight")
            if not tracking_number:
                self.send_json_response(400, {"status": "error", "message": "Missing trackingNumber"})
                return
                
            try:
                # Load custom selectors if any
                selectors = None
                if os.path.exists(SETTINGS_FILE):
                    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                        settings = json.load(f)
                        selectors = settings.get("selectors")
                
                success = run_async(automation.upload_to_jms(tracking_number, weight, selectors))
                
                # Update status in scanned_packages.json
                scanned_path = os.path.join(DATA_DIR, "scanned_packages.json")
                if os.path.exists(scanned_path):
                    with FileLock(scanned_path + '.lock', timeout=5), open(scanned_path, "r", encoding="utf-8") as f:
                        packages = json.load(f)
                    package = next((p for p in packages if p["trackingNumber"] == tracking_number), None)
                    if package:
                        package["jmsStatus"] = "Thành công"
                        with FileLock(scanned_path + '.lock', timeout=5), open(scanned_path, "w", encoding="utf-8") as f:
                            json.dump(packages, f, ensure_ascii=False, indent=4)
                            
                self.send_json_response(200, {"status": "success", "message": f"Uploaded successfully for {tracking_number}"})
            except Exception as e:
                # Update status in scanned_packages.json
                scanned_path = os.path.join(DATA_DIR, "scanned_packages.json")
                if os.path.exists(scanned_path):
                    with FileLock(scanned_path + '.lock', timeout=5), open(scanned_path, "r", encoding="utf-8") as f:
                        packages = json.load(f)
                    package = next((p for p in packages if p["trackingNumber"] == tracking_number), None)
                    if package:
                        package["jmsStatus"] = f"Thất bại: {str(e)[:50]}"
                        with FileLock(scanned_path + '.lock', timeout=5), open(scanned_path, "w", encoding="utf-8") as f:
                            json.dump(packages, f, ensure_ascii=False, indent=4)
                            
                self.send_json_response(500, {"status": "error", "message": str(e)})

        elif path == "/api/update-copied":
            tracking_number = body.get("trackingNumber")
            copied = body.get("copied", True)
            if not tracking_number:
                self.send_json_response(400, {"status": "error", "message": "Missing trackingNumber"})
                return
            try:
                scanned_path = os.path.join(DATA_DIR, "scanned_packages.json")
                if os.path.exists(scanned_path):
                    with FileLock(scanned_path + '.lock', timeout=5), open(scanned_path, "r", encoding="utf-8") as f:
                        packages = json.load(f)
                    package = next((p for p in packages if p["trackingNumber"] == tracking_number), None)
                    if package:
                        package["copied"] = copied
                        with FileLock(scanned_path + '.lock', timeout=5), open(scanned_path, "w", encoding="utf-8") as f:
                            json.dump(packages, f, ensure_ascii=False, indent=4)
                self.send_json_response(200, {"status": "success"})
            except Exception as e:
                self.send_json_response(500, {"status": "error", "message": str(e)})

        elif path == "/api/active-tracking":
            tracking_number = body.get("trackingNumber")
            automation.last_copied_tracking = tracking_number
            self.send_json_response(200, {"status": "success"})

        elif path == "/api/launch-popup":
            try:
                import subprocess
                python_exe = sys.executable or "python"
                # If compiled with PyInstaller, launch self with --popup flag to avoid port collisions
                if hasattr(sys, '_MEIPASS'):
                    subprocess.Popen([python_exe, "--popup"], close_fds=True if os.name != 'nt' else False)
                else:
                    popup_script = os.path.join(os.path.dirname(__file__), "..", "popup_tool.py")
                    popup_script = os.path.abspath(popup_script)
                    subprocess.Popen([python_exe, popup_script], close_fds=True if os.name != 'nt' else False)
                self.send_json_response(200, {"status": "success", "message": "Popup tool launched successfully"})
            except Exception as e:
                self.send_json_response(500, {"status": "error", "message": str(e)})

        elif path == "/api/add-manual-package":
            tracking_number = body.get("trackingNumber")
            weight = body.get("weight")
            files = body.get("files", [])
            
            if not tracking_number:
                self.send_json_response(400, {"status": "error", "message": "Missing trackingNumber"})
                return
                
            try:
                # Load existing packages list first to determine folderName
                scanned_path = os.path.join(DATA_DIR, "scanned_packages.json")
                packages = []
                if os.path.exists(scanned_path):
                    with FileLock(scanned_path + '.lock', timeout=5), open(scanned_path, "r", encoding="utf-8") as f:
                        try:
                            packages = json.load(f)
                        except Exception:
                            packages = []

                # Find existing package or calculate a new folderName
                existing_pkg = next((p for p in packages if p["trackingNumber"] == tracking_number), None)
                if existing_pkg and "folderName" in existing_pkg:
                    folder_name = existing_pkg["folderName"]
                else:
                    max_idx = 0
                    for p in packages:
                        if "folderName" in p:
                            try:
                                val = int(p["folderName"])
                                if val > max_idx:
                                    max_idx = val
                            except ValueError:
                                pass
                    folder_name = str(max_idx + 1)
                
                package_dir = os.path.join(DATA_DIR, folder_name)
                os.makedirs(package_dir, exist_ok=True)
                
                # Write tracking number & weight txt file inside package folder
                weight_str = f"{weight}" if weight is not None else "0"
                txt_path = os.path.join(package_dir, f"{tracking_number}.txt")
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(f"{tracking_number}\n{weight_str}\n\nMã vận đơn: {tracking_number}\nCân nặng: {weight_str} kg\n")
                
                saved_images = []
                saved_videos = []
                
                for idx, file_info in enumerate(files):
                    name = file_info.get("name", "")
                    b64data = file_info.get("data")
                    content_type = file_info.get("type", "")
                    
                    if not b64data:
                        continue
                        
                    # Determine file extension
                    ext = ".jpg"
                    if "video" in content_type or name.lower().endswith((".mp4", ".mov", ".avi")):
                        ext = ".mp4"
                    elif "png" in content_type or name.lower().endswith(".png"):
                        ext = ".png"
                    elif "gif" in content_type or name.lower().endswith(".gif"):
                        ext = ".gif"
                        
                    filename = f"manual_{idx+1}{ext}"
                    filepath = os.path.join(package_dir, filename)
                    
                    # If base64 contains header, remove it
                    if "," in b64data:
                        b64data = b64data.split(",")[1]
                        
                    with open(filepath, "wb") as f:
                        f.write(base64.b64decode(b64data))
                        
                    web_path = f"/data/{folder_name}/{filename}"
                    if ext == ".mp4":
                        saved_videos.append(web_path)
                    else:
                        saved_images.append(web_path)
                
                # Check if package already exists, update it, else prepend
                existing_idx = next((i for i, p in enumerate(packages) if p["trackingNumber"] == tracking_number), -1)
                new_pkg = {
                    "trackingNumber": tracking_number,
                    "weight": weight,
                    "images": saved_images,
                    "videos": saved_videos,
                    "localStatus": "Đã tải về",
                    "jmsStatus": "Chưa xử lý",
                    "folderName": folder_name
                }
                
                if existing_idx != -1:
                    # Preserve copied and jmsStatus status if they exist
                    if "copied" in packages[existing_idx]:
                        new_pkg["copied"] = packages[existing_idx]["copied"]
                    if "jmsStatus" in packages[existing_idx] and packages[existing_idx]["jmsStatus"] != "Chưa xử lý":
                        new_pkg["jmsStatus"] = packages[existing_idx]["jmsStatus"]
                    packages[existing_idx] = new_pkg
                else:
                    packages.insert(0, new_pkg)
                    
                with FileLock(scanned_path + '.lock', timeout=5), open(scanned_path, "w", encoding="utf-8") as f:
                    json.dump(packages, f, ensure_ascii=False, indent=4)
                    
                self.send_json_response(200, {"status": "success", "package": new_pkg})
            except Exception as e:
                self.send_json_response(500, {"status": "error", "message": str(e)})

        elif path == "/api/settings":
            try:
                with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(body, f, ensure_ascii=False, indent=4)
                self.send_json_response(200, {"status": "success", "message": "Settings saved"})
            except Exception as e:
                self.send_json_response(500, {"status": "error", "message": str(e)})
        else:
            self.send_response(404)
            self.end_headers()

    def handle_get_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                self.send_json_response(200, settings)
            except Exception as e:
                self.send_json_response(500, {"error": str(e)})
        else:
            # Default settings
            self.send_json_response(200, {
                "selectors": {
                    "search_input": "input[placeholder*='vận đơn'], input[id*='billCode'], .el-input__inner",
                    "search_btn": "button:has-text('Tìm kiếm'), button:has-text('Search'), .el-button--primary",
                    "edit_btn": "i.el-icon-edit, button[title*='Nhập liệu'], .el-table__row button:first-child",
                    "weight_input": "input[placeholder*='trọng lượng'], input[placeholder*='cân nặng'], .el-dialog input.el-input__inner",
                    "upload_plus_btn": ".el-upload--picture-card, input[type='file']",
                    "confirm_btn": "button:has-text('Xác nhận'), button:has-text('Lưu'), .el-dialog__footer button.el-button--primary"
                },
                "zalo_selectors": {
                    "chat_item": ".chat-item",
                    "scroll_container": ".transform-gpu",
                    "search_inchat": ".search-message-inchat",
                    "reaction_space": ".message-reaction-v2-space",
                    "conv_item": ".conv-item, [class*='conv'], .msg-item, div, span",
                    "pinned_banner": ".list-chat-box-banner, [class*='list-chat-box-banner'], .chat-group-topic, [class*='pinned-message']"
                },
                "enable_ocr_check": False,
                "ocr_api_key": "helloworld"
            })

    def handle_get_packages(self):
        scanned_path = os.path.join(DATA_DIR, "scanned_packages.json")
        if os.path.exists(scanned_path):
            try:
                with FileLock(scanned_path + '.lock', timeout=5), open(scanned_path, "r", encoding="utf-8") as f:
                    packages = json.load(f)
                self.send_json_response(200, packages)
            except Exception as e:
                self.send_json_response(500, {"error": str(e)})
        else:
            self.send_json_response(200, [])

    def send_json_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

def start_server():
    server_address = ('localhost', 5050)
    httpd = ThreadingHTTPServer(server_address, JMSHandler)
    print(f"Server is running at http://localhost:5050")
    
    # Auto open browser to control UI
    webbrowser.open("http://localhost:5050")
    
    httpd.serve_forever()

def main():
    global main_loop
    # Start HTTP server in a daemon thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # Run Playwright event loop in the main thread
    main_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(main_loop)
    try:
        main_loop.run_forever()
    except KeyboardInterrupt:
        print("Stopping server...")
        # Clean up playwright
        main_loop.run_until_complete(automation.close_browser())
        sys.exit(0)

if __name__ == "__main__":
    main()
