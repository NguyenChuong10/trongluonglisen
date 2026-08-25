import os
import re
import base64
import json
import asyncio
import mimetypes
import sys
import shutil
import time
import requests
import cv2
import zxingcpp
from playwright.async_api import async_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
if hasattr(sys, '_MEIPASS'):
    exe_dir = os.path.dirname(sys.executable)
    USER_DATA_DIR = os.path.abspath(os.path.join(exe_dir, "user_data"))
    DATA_DIR = os.path.abspath(os.path.join(exe_dir, "data"))
    SETTINGS_FILE = os.path.abspath(os.path.join(exe_dir, "settings.json"))
else:
    USER_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "user_data"))
    DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    SETTINGS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "settings.json"))

JS_JUMP_TO_TRACKING = r"""
async (trk) => {
    // Dismiss left global search panel if open to prevent blocking header clicks
    const globalCloseBtn = Array.from(document.querySelectorAll('*')).find(el => {
        const text = (el.textContent || '').trim();
        const rect = el.getBoundingClientRect();
        return text === 'Đóng' && rect.width > 0 && rect.left < 400;
    });
    if (globalCloseBtn) {
        globalCloseBtn.click();
        await new Promise(resolve => setTimeout(resolve, 300));
    }

    const sidebar = document.querySelector(window.zalo_search_inchat || '.search-message-inchat');
    const isSidebarOpen = sidebar && sidebar.getBoundingClientRect().width > 0;
    
    if (!isSidebarOpen) {
        // Find and click the search icon in the chat header
        let searchBtn = document.querySelector('.search-message-entry, [title*="Tìm kiếm"], [title*="Search"], .chat-header-search');
        if (!searchBtn) {
            const icons = Array.from(document.querySelectorAll('i, span, div, button'));
            searchBtn = icons.find(el => {
                const className = (el.className || '').toLowerCase();
                const title = (el.getAttribute('title') || '').toLowerCase();
                return (className.includes('search') || title.includes('tìm kiếm')) && el.getBoundingClientRect().width > 0;
            });
        }
        if (!searchBtn) return false;
        
        // Remove disabled and click the search button
        searchBtn.removeAttribute('data-disabled');
        searchBtn.click();
        
        // Wait up to 2.5 seconds for the sidebar search input to render
        for (let i = 0; i < 25; i++) {
            await new Promise(resolve => setTimeout(resolve, 100));
            if (document.querySelector('input.search-message-input__editor')) break;
        }
    }
    
    // Find the sidebar search input
    const searchInput = document.querySelector('input.search-message-input__editor');
    if (!searchInput) return false;
    
    searchInput.focus();
    // React value setter workaround
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    if (nativeInputValueSetter) {
        nativeInputValueSetter.call(searchInput, trk);
    } else {
        searchInput.value = trk;
    }
    searchInput.dispatchEvent(new Event('input', { bubbles: true }));
    searchInput.dispatchEvent(new Event('change', { bubbles: true }));
    
    // Allow React state sync before Enter key is dispatched
    await new Promise(resolve => setTimeout(resolve, 200));
    
    const enterOpts = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true };
    searchInput.dispatchEvent(new KeyboardEvent('keydown', enterOpts));
    searchInput.dispatchEvent(new KeyboardEvent('keypress', enterOpts));
    searchInput.dispatchEvent(new KeyboardEvent('keyup', enterOpts));
    
    // Wait up to 3 seconds for search results to load
    let textNode = null;
    for (let i = 0; i < 30; i++) {
        const activeSidebar = document.querySelector(window.zalo_search_inchat || '.search-message-inchat');
        const parentEl = activeSidebar || document;
        const elements = Array.from(parentEl.querySelectorAll('*'));
        textNode = elements.find(el => {
            const rect = el.getBoundingClientRect();
            return el.childNodes.length === 1 && el.childNodes[0].nodeType === 3 && el.textContent.includes(trk) && rect.width > 0;
        });
        if (textNode) break;
        
        const emptyEl = activeSidebar ? activeSidebar.querySelector('.search-message-empty, [class*="empty"]') : null;
        if (emptyEl && emptyEl.getBoundingClientRect().width > 0 && emptyEl.innerText.includes('Không tìm thấy')) {
            break;
        }
        
        await new Promise(resolve => setTimeout(resolve, 100));
    }
    
    if (textNode) {
        let clickTarget = textNode;
        let clicked = false;
        for (let d = 0; d < 6 && clickTarget; d++) {
            const cName = String(clickTarget.className || '').toLowerCase();
            const tagName = clickTarget.tagName.toLowerCase();
            if (cName.includes('item') || cName.includes('card') || cName.includes('row') || tagName === 'li' || tagName === 'a') {
                clickTarget.click();
                clicked = true;
                break;
            }
            clickTarget = clickTarget.parentElement;
        }
        if (!clicked) {
            textNode.click();
        }
        
        await new Promise(resolve => setTimeout(resolve, 800));
        
        // Close the search sidebar
        const closeBtn = document.querySelector('.search-message-inchat__header__right-btn, .fa-Close_24_Line, [class*="sidebar"] [class*="close"], [class*="sidebar"] .zicon-close, [class*="search"] [class*="close"]');
        if (closeBtn) {
            closeBtn.click();
            const innerI = closeBtn.querySelector('i');
            if (innerI) innerI.click();
        }
        return true;
    }
    
    return false;
}
"""

class JMSAutomation:
    def __init__(self):
        self.playwright = None
        self.browser_context = None
        self.zalo_page = None
        self.jms_page = None
        self.last_copied_tracking = None
        self.current_action_progress = ""
        self.stop_requested = False

    async def resolve_pinned_tracking(self):
        """
        Xử lý định vị tin nhắn ghim:
        1. Tìm banner ghim và trích xuất từ khóa.
        2. Click banner ghim để cuộn đến tin nhắn.
        3. Phân tích DOM tin nhắn để đối chiếu và tìm mã vận đơn đầy đủ.
        """
        try:
            # 1. Tìm thông tin banner ghim
            info = await self.zalo_page.evaluate("""
                async () => {
                    const selectors = [
                        '.list-chat-box-banner',
                        '[class*="list-chat-box-banner"]',
                        '.chat-group-topic',
                        '[class*="chat-group-topic"]',
                        '[class*="pinned-message"]'
                    ];
                    let bannerEl = null;
                    for (const selector of selectors) {
                        const elements = Array.from(document.querySelectorAll(selector));
                        const visible = elements.find(el => {
                            const r = el.getBoundingClientRect();
                            return r.width > 0 && r.height > 0;
                        });
                        if (visible) {
                            bannerEl = visible;
                            break;
                        }
                    }
                    if (!bannerEl) {
                        return null;
                    }
                    const bannerText = (bannerEl.innerText || bannerEl.textContent || '').trim();
                    const noiseWords = ["tin", "ghim", "xem", "thêm", "pin", "pinned", "message", "announcement", "board", "banner", "chốt", "mốc"];
                    const rawTokens = bannerText.toLowerCase().split(/[\\s,\\n\\r\\t\\-:;\\!\\[\\]()]+/);
                    const keywords = [];
                    for (let token of rawTokens) {
                        token = token.replace(/(\\.|\\u2026)+$/, '').trim();
                        if (token.length >= 2 && !noiseWords.includes(token)) {
                            keywords.push(token);
                        }
                    }
                    let directTracking = null;
                    const directMatch = bannerText.match(/\\b\\d{11,12}\\b/);
                    if (directMatch) {
                        directTracking = directMatch[0];
                    }
                    return {
                        bannerText: bannerText,
                        keywords: keywords,
                        directTracking: directTracking
                    };
                }
            """)

            if not info:
                print("[resolve_pinned_tracking] Không phát hiện banner ghim nào.")
                return None

            print(f"[resolve_pinned_tracking] Phát hiện banner: '{info['bannerText']}'. Từ khóa đối chiếu: {info['keywords']}")

            # 2. Click vào banner ghim
            banner_selectors = [
                '.list-chat-box-banner',
                '[class*="list-chat-box-banner"]',
                '.chat-group-topic',
                '[class*="pinned-message"]',
                '[class*="pinned"]',
                '[class*="pin"]',
                '[class*="announce"]',
                '[class*="board"]',
                '[class*="banner"]'
            ]
            
            clicked = False
            for selector in banner_selectors:
                try:
                    locator = self.zalo_page.locator(selector).first
                    if await locator.is_visible() and await locator.bounding_box():
                        print(f"[resolve_pinned_tracking] Đang click banner qua locator: {selector}")
                        await locator.click(timeout=3000)
                        clicked = True
                        break
                except Exception as ex:
                    print(f"[resolve_pinned_tracking] Lỗi click banner với selector {selector}: {ex}")

            if not clicked:
                # Fallback click via JS
                clicked = await self.zalo_page.evaluate("""
                    () => {
                        const selectors = [
                            '.list-chat-box-banner',
                            '[class*="list-chat-box-banner"]',
                            '.chat-group-topic',
                            '[class*="pinned-message"]',
                            '[class*="pinned"]',
                            '[class*="pin"]',
                            '[class*="announce"]',
                            '[class*="board"]',
                            '[class*="banner"]'
                        ];
                        for (const selector of selectors) {
                            const elements = Array.from(document.querySelectorAll(selector));
                            const visible = elements.find(el => {
                                const r = el.getBoundingClientRect();
                                return r.width > 0 && r.height > 0;
                            });
                            if (visible) {
                                visible.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                if clicked:
                    print("[resolve_pinned_tracking] Đã click banner bằng JS fallback.")

            if clicked:
                # Đợi Zalo Web cuộn và tải tin nhắn
                await asyncio.sleep(2.0)
            else:
                print("[resolve_pinned_tracking] Không thể click banner ghim.")

            # 3. Phân tích DOM tìm tin nhắn trùng khớp và trích xuất mã vận đơn (Có Polling)
            match_result = await self.zalo_page.evaluate("""
                async (args) => {
                    const keywords = args.keywords || [];
                    const directTracking = args.directTracking;
                    
                    const extractTracking = (item) => {
                        const text = (item.innerText || '').trim();
                        const match = text.match(/\\b\\d{11,12}\\b/);
                        return match ? match[0] : null;
                    };
                    
                    // Thăm dò DOM liên tục trong tối đa 5 giây để đợi Zalo Web tải tin nhắn
                    for (let attempt = 0; attempt < 10; attempt++) {
                        const allMsgItems = Array.from(document.querySelectorAll(window.zalo_chat_item || '.chat-item'));
                        if (allMsgItems.length > 0) {
                            let bestIdx = -1;
                            let bestScore = -1;
                            
                            allMsgItems.forEach((item, idx) => {
                                const text = (item.innerText || '').toLowerCase();
                                let score = 0;
                                for (const kw of keywords) {
                                    if (text.includes(kw)) {
                                        if (/^\\d+$/.test(kw)) {
                                            score += 3;
                                        } else {
                                            score += 1;
                                        }
                                    }
                                }
                                if (directTracking && text.includes(directTracking.toLowerCase())) {
                                    score += 10;
                                }
                                if (score > bestScore) {
                                    bestScore = score;
                                    bestIdx = idx;
                                }
                            });
                            
                            if (bestIdx !== -1 && bestScore > 0) {
                                let resolvedTracking = extractTracking(allMsgItems[bestIdx]);
                                if (resolvedTracking) {
                                    return { success: true, tracking: resolvedTracking, matchedIdx: bestIdx, score: bestScore };
                                }
                            }
                        }
                        await new Promise(resolve => setTimeout(resolve, 500));
                    }
                    
                    // Fallback nếu không có kết quả điểm cao
                    const allMsgItems = Array.from(document.querySelectorAll(window.zalo_chat_item || '.chat-item'));
                    if (directTracking && allMsgItems.length > 0) {
                        const foundIdx = allMsgItems.findIndex(item => (item.innerText || '').includes(directTracking));
                        if (foundIdx !== -1) {
                            return { success: true, tracking: directTracking, matchedIdx: foundIdx, score: 999 };
                        }
                    }
                    
                    return { success: false, error: 'Không tìm thấy tin nhắn ghim trong DOM sau 5 giây cuộn.' };
                }
            """, {"keywords": info["keywords"], "directTracking": info["directTracking"]})

            if match_result.get("success"):
                print(f"[resolve_pinned_tracking] Định vị thành công: {match_result['tracking']} (Index: {match_result['matchedIdx']}, Score: {match_result['score']}, Note: {match_result.get('note', 'Trực tiếp')})")
                return match_result["tracking"]
            else:
                print(f"[resolve_pinned_tracking] Lỗi phân tích tin ghim: {match_result.get('error')}")
                return None

        except Exception as e:
            print(f"[resolve_pinned_tracking] Gặp ngoại lệ khi định vị tin ghim: {e}")
            return None

    async def jump_to_tracking(self, tracking_number):
        """Helper to open Zalo search sidebar, input the tracking number, click the result to jump, and close sidebar."""
        print(f"[Zalo Scanner] Đang định vị mã mốc {tracking_number}...")
        try:
            # 1. Open the search sidebar using JS
            opened = await self.zalo_page.evaluate("""
                async () => {
                    // Dismiss left global search panel if open to prevent blocking header clicks
                    const globalCloseBtn = Array.from(document.querySelectorAll('*')).find(el => {
                        const text = (el.textContent || '').trim();
                        const rect = el.getBoundingClientRect();
                        return text === 'Đóng' && rect.width > 0 && rect.left < 400;
                    });
                    if (globalCloseBtn) {
                        globalCloseBtn.click();
                        await new Promise(resolve => setTimeout(resolve, 300));
                    }

                    const sidebar = document.querySelector(window.zalo_search_inchat || '.search-message-inchat');
                    const isSidebarOpen = sidebar && sidebar.getBoundingClientRect().width > 0;
                    if (!isSidebarOpen) {
                        let searchBtn = document.querySelector('.search-message-entry, [title*="Tìm kiếm"], [title*="Search"], .chat-header-search');
                        if (!searchBtn) {
                            const icons = Array.from(document.querySelectorAll('i, span, div, button'));
                            searchBtn = icons.find(el => {
                                const className = (el.className || '').toLowerCase();
                                const title = (el.getAttribute('title') || '').toLowerCase();
                                return (className.includes('search') || title.includes('tìm kiếm')) && el.getBoundingClientRect().width > 0;
                            });
                        }
                        if (searchBtn) {
                            searchBtn.removeAttribute('data-disabled');
                            searchBtn.click();
                            const innerI = searchBtn.querySelector('i');
                            if (innerI) {
                                innerI.removeAttribute('data-disabled');
                                innerI.click();
                            }
                            return true;
                        }
                        return false;
                    }
                    return true;
                }
            """)
            if not opened:
                print("[Zalo Scanner] Không tìm thấy nút tìm kiếm tin nhắn trong chat header.")
                return False

            # 2. Wait for search input to be rendered
            await self.zalo_page.wait_for_selector('input.search-message-input__editor', timeout=5000)
            
            # 3. Focus, clear, and type tracking number
            search_input = self.zalo_page.locator('input.search-message-input__editor').first
            await search_input.click()
            await self.zalo_page.keyboard.press('Control+A')
            await self.zalo_page.keyboard.press('Backspace')
            await asyncio.sleep(0.2)
            await search_input.type(tracking_number, delay=50)
            await self.zalo_page.keyboard.press('Enter')
            
            # 4. Wait for search results
            found_result = False
            for _ in range(45):
                await asyncio.sleep(0.1)
                res = await self.zalo_page.evaluate("""
                    (trk) => {
                        const sidebar = document.querySelector(window.zalo_search_inchat || '.search-message-inchat');
                        if (!sidebar) return { state: 'no_sidebar' };
                        const items = Array.from(sidebar.querySelectorAll('.search-message__item'));
                        const target = items.find(item => item.textContent.includes(trk));
                        if (target) return { state: 'found' };
                        
                        const emptyEl = sidebar.querySelector('.search-message-empty, [class*="empty"]');
                        if (emptyEl && emptyEl.getBoundingClientRect().width > 0 && emptyEl.innerText.includes('Không tìm thấy')) {
                            return { state: 'empty' };
                        }
                        return { state: 'searching' };
                    }
                """, tracking_number)
                if res.get("state") == "found":
                    found_result = True
                    break
                elif res.get("state") == "empty":
                    break
            
            if not found_result:
                print(f"[Zalo Scanner] Không tìm thấy kết quả tìm kiếm cho mã mốc {tracking_number}.")
                return False

            # 5. Click on the search result
            clicked = await self.zalo_page.evaluate("""
                (trk) => {
                    const sidebar = document.querySelector(window.zalo_search_inchat || '.search-message-inchat');
                    if (!sidebar) return false;
                    const items = Array.from(sidebar.querySelectorAll('.search-message__item'));
                    const target = items.find(item => item.textContent.includes(trk));
                    if (target) {
                        target.removeAttribute('data-disabled');
                        target.click();
                        return true;
                    }
                    return false;
                }
            """, tracking_number)
            
            if clicked:
                print(f"[Zalo Scanner] Đã định vị thành công mã mốc {tracking_number}. Chờ tải và scroll tin nhắn...")
                await asyncio.sleep(3.5)
                
                # 6. Close the search sidebar
                await self.zalo_page.evaluate("""
                    () => {
                        const closeBtn = document.querySelector('.search-message-inchat__header__right-btn, .fa-Close_24_Line, [class*="sidebar"] [class*="close"], [class*="sidebar"] .zicon-close, [class*="search"] [class*="close"]');
                        if (closeBtn) {
                            closeBtn.removeAttribute('data-disabled');
                            closeBtn.click();
                            const innerI = closeBtn.querySelector('i');
                            if (innerI) {
                                innerI.removeAttribute('data-disabled');
                                innerI.click();
                            }
                        }
                    }
                """)
                await asyncio.sleep(0.5)
                return True
            else:
                return False
        except Exception as e:
            print(f"[Zalo Scanner] Lỗi định vị mã mốc {tracking_number}: {e}")
            return False

    async def inject_zalo_selectors(self):
        zalo_selectors = {
            "chat_item": ".chat-item",
            "scroll_container": ".transform-gpu",
            "search_inchat": ".search-message-inchat",
            "reaction_space": ".message-reaction-v2-space",
            "conv_item": ".conv-item, [class*='conv'], .msg-item, div, span",
            "pinned_banner": ".list-chat-box-banner, [class*='list-chat-box-banner'], .chat-group-topic, [class*='pinned-message']"
        }
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                    if "zalo_selectors" in settings:
                        zalo_selectors.update(settings["zalo_selectors"])
        except Exception as e:
            print(f"Lỗi đọc settings Zalo: {e}")
            
        script = f"""
            window.zalo_chat_item = `{zalo_selectors['chat_item']}`;
            window.zalo_scroll_container = `{zalo_selectors['scroll_container']}`;
            window.zalo_search_inchat = `{zalo_selectors['search_inchat']}`;
            window.zalo_reaction_space = `{zalo_selectors['reaction_space']}`;
            window.zalo_conv_item = `{zalo_selectors['conv_item']}`;
            window.zalo_pinned_banner = `{zalo_selectors['pinned_banner']}`;
        """
        if self.browser_context:
            await self.browser_context.add_init_script(script)

    async def start_browser(self):
        """Launches the user's Chrome browser with a persistent profile."""
        if self.browser_context:
            try:
                # Check if context is active and has open pages
                pages = self.browser_context.pages
                if len(pages) > 0:
                    return True
            except Exception:
                pass
            # Previous context is closed or invalid, clean it up
            try:
                await self.close_browser()
            except Exception:
                pass
            self.browser_context = None
            
        os.makedirs(USER_DATA_DIR, exist_ok=True)
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # Clean up any leftover browser locks or zombie processes
        self.cleanup_browser_locks()
        
        self.playwright = await async_playwright().start()
        
        # Launch persistent Chrome context to save login sessions
        self.browser_context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            channel="chrome",
            args=["--start-maximized", "--remote-debugging-port=9222"],
            no_viewport=True
        )
        
        await self.inject_zalo_selectors()
        
        # Open Zalo and JMS tabs if not already open
        pages = self.browser_context.pages
        if len(pages) == 0:
            self.zalo_page = await self.browser_context.new_page()
            await self.zalo_page.goto("https://chat.zalo.me/")
        else:
            self.zalo_page = pages[0]
            await self.zalo_page.goto("https://chat.zalo.me/")

        self.jms_page = await self.browser_context.new_page()
        await self.jms_page.goto("https://jms.jtexpress.vn/")
        
        # Setup file chooser listener on context to handle dynamically created pages/tabs
        self.browser_context.on("page", lambda p: self.setup_file_chooser_interceptor(p))
        
        # Apply to already opened pages
        for page in self.browser_context.pages:
            self.setup_file_chooser_interceptor(page)
            
        return True

    def setup_file_chooser_interceptor(self, page):
        """Attaches a file chooser listener to the given page."""
        page.on("filechooser", lambda fc: asyncio.create_task(self.handle_file_chooser(fc, page)))
        print(f"[File Interceptor] Attached file chooser listener on page: {page.url}")

    async def handle_file_chooser(self, file_chooser, page):
        """Automatically selects and uploads the files corresponding to the active tracking number."""
        print(f"[File Interceptor] Intercepted file chooser on: {page.url}")
        
        try:
            # 1. Try to extract the tracking number from J&T input elements
            tracking_number = await page.evaluate("""
                () => {
                    // Method A: Look for input containing exactly 12 digits
                    const inputs = Array.from(document.querySelectorAll('input'));
                    for (const input of inputs) {
                        const val = (input.value || '').trim();
                        if (/^\\d{11,12}$/.test(val)) {
                            return val;
                        }
                    }
                    
                    // Method B: Find J&T input fields inside the modal dialog
                    // Look for label containing 'Mã vận đơn'
                    const labels = Array.from(document.querySelectorAll('label, span, div'));
                    for (const label of labels) {
                        const text = (label.textContent || label.innerText || '').trim();
                        if (text.includes('Mã vận đơn')) {
                            // Search parent and form-item structure
                            let parent = label.parentElement;
                            for (let d = 0; d < 4 && parent; d++) {
                                const input = parent.querySelector('input');
                                if (input) {
                                    const val = (input.value || '').trim();
                                    if (/^\\d{11,12}$/.test(val)) {
                                        return val;
                                    }
                                }
                                parent = parent.parentElement;
                            }
                        }
                    }
                    return null;
                }
            """)
            
            # 2. If DOM extraction fails, fall back to the last copied tracking number
            if not tracking_number:
                tracking_number = self.last_copied_tracking
                print(f"[File Interceptor] Could not find tracking number in DOM. Using last copied fallback: {tracking_number}")
            else:
                print(f"[File Interceptor] Extracted tracking number from DOM: {tracking_number}")
                
            if not tracking_number:
                print("[File Interceptor] No tracking number found. Letting user choose manually...")
                return
                
            # 3. Resolve package directory on disk
            package_dir = None
            for item in os.listdir(DATA_DIR):
                item_path = os.path.join(DATA_DIR, item)
                if os.path.isdir(item_path):
                    if os.path.exists(os.path.join(item_path, f"{tracking_number}.txt")):
                        package_dir = item_path
                        break
            
            # Fallback to direct tracking number folder
            if not package_dir:
                fallback_dir = os.path.join(DATA_DIR, tracking_number)
                if os.path.exists(fallback_dir) and os.path.isdir(fallback_dir):
                    package_dir = fallback_dir
                    
            if not package_dir:
                print(f"[File Interceptor] No data directory found for tracking number {tracking_number}.")
                return
                
            # 4. Read all files (except .txt metadata)
            files = [
                os.path.join(package_dir, f)
                for f in os.listdir(package_dir)
                if os.path.isfile(os.path.join(package_dir, f)) and not f.lower().endswith('.txt')
            ]
            
            if len(files) == 0:
                print(f"[File Interceptor] No uploadable files in folder: {package_dir}")
                return
                
            print(f"[File Interceptor] Auto uploading {len(files)} files for {tracking_number}: {files}")
            
            # 5. Set the files on the file chooser
            await file_chooser.set_files(files)
            print("[File Interceptor] Upload complete!")
            
        except Exception as e:
            print(f"[File Interceptor] Error handling file chooser: {e}")

    async def get_status(self):
        """Returns the connection status of Zalo and JMS tabs."""
        if not self.browser_context:
            return {"browser": "disconnected", "zalo": "disconnected", "jms": "disconnected", "progress": self.current_action_progress}
            
        status = {"browser": "connected", "zalo": "disconnected", "jms": "disconnected", "progress": self.current_action_progress}
        
        for page in self.browser_context.pages:
            url = page.url
            if "zalo.me" in url:
                status["zalo"] = "connected"
                self.zalo_page = page
            if "jms.jtexpress.vn" in url:
                status["jms"] = "connected"
                self.jms_page = page
                
        return status

    async def scan_zalo(self, direction="down", start_tracking=None):
        """Scrapes the active Zalo chat for packages (tracking number + weight + media)."""
        status = await self.get_status()
        if status["zalo"] == "disconnected":
            raise Exception("Chưa mở hoặc chưa kết nối được tab Zalo Web!")

        # Bring Zalo tab to front to ensure DOM is active
        await self.zalo_page.bring_to_front()
        
        # Tự động tìm kiếm và mở nhóm chat "HÀNG QUÁ TRỌNG LƯỢNG"
        print("[Zalo Scanner] Đang tìm kiếm nhóm 'HÀNG QUÁ TRỌNG LƯỢNG'...")
        try:
            search_input = self.zalo_page.locator('#contact-search-input, input[placeholder*="Tìm"], input[placeholder*="Search"]').first
            await search_input.click(timeout=5000)
            await search_input.fill("HÀNG QUÁ TRỌNG LƯỢNG")
            await asyncio.sleep(2.0)
            
            group_clicked = await self.zalo_page.evaluate("""
                () => {
                    const items = Array.from(document.querySelectorAll(window.zalo_conv_item || '.conv-item, [class*="conv"], .msg-item, div, span'));
                    const match = items.find(el => {
                        const text = (el.textContent || '').trim();
                        return text === 'HÀNG QUÁ TRỌNG LƯỢNG' && el.getBoundingClientRect().width > 0;
                    });
                    if (match) {
                        let clickTarget = match;
                        while (clickTarget && clickTarget.tagName !== 'BODY') {
                            if (clickTarget.className && (clickTarget.className.includes('conv-item') || clickTarget.className.includes('msg-item'))) {
                                clickTarget.click();
                                return true;
                            }
                            clickTarget = clickTarget.parentElement;
                        }
                    }
                    return false;
                }
            """)
            if group_clicked:
                print("[Zalo Scanner] Đã chọn nhóm 'HÀNG QUÁ TRỌNG LƯỢNG'. Chờ tải tin nhắn...")
                await asyncio.sleep(3.0)
        except Exception as e:
            print(f"[Zalo Scanner] Lỗi tự động chọn nhóm: {e}")
        
        # If start_tracking is provided, locate it using Zalo Search or fallback to scroll-up
        pinned_tracking = None
        if start_tracking:
            found = await self.jump_to_tracking(start_tracking)
            if not found:
                print(f"[Zalo Scanner] Không tìm thấy mã mốc qua tìm kiếm Zalo. Thử cuộn lên để tìm mốc...")
                found_fallback = await self.zalo_page.evaluate("""
                    async (trk) => {
                        const scrollContainer = document.querySelector(window.zalo_scroll_container || '.transform-gpu') || Array.from(document.querySelectorAll('div')).reduce(function(best,el){var s=window.getComputedStyle(el),r=el.getBoundingClientRect();if((s.overflowY==='scroll'||s.overflowY==='auto')&&r.height>400&&r.width>400&&el.scrollHeight>el.clientHeight+100){if(!best||el.scrollHeight>best.scrollHeight)return el;}return best;},null);
                        if (!scrollContainer) return false;
                        const isVisible = () => {
                            const chatItems = Array.from(document.querySelectorAll(window.zalo_chat_item || '.chat-item'));
                            return chatItems.some(item => (item.innerText || '').includes(trk));
                        };
                        if (isVisible()) return true;
                        
                        let lastScrollTop = scrollContainer.scrollTop;
                        let lastScrollHeight = scrollContainer.scrollHeight;
                        let sameCount = 0;
                        for (let i = 0; i < 40; i++) {
                            if (scrollContainer.scrollTop <= 5) {
                                scrollContainer.scrollTop = 15;
                                scrollContainer.dispatchEvent(new Event('scroll', { bubbles: true }));
                                scrollContainer.scrollTop = 0;
                            } else {
                                scrollContainer.scrollTop -= 1000;
                            }
                            scrollContainer.dispatchEvent(new Event('scroll', { bubbles: true }));
                            scrollContainer.dispatchEvent(new WheelEvent('wheel', { deltaY: -1000, bubbles: true }));
                            await new Promise(resolve => setTimeout(resolve, 300));
                            if (isVisible()) return true;
                            if (scrollContainer.scrollTop === lastScrollTop && scrollContainer.scrollHeight === lastScrollHeight) {
                                sameCount++;
                                if (sameCount >= 5) break;
                            } else {
                                sameCount = 0;
                            }
                            lastScrollTop = scrollContainer.scrollTop;
                            lastScrollHeight = scrollContainer.scrollHeight;
                        }
                        return false;
                    }
                """, start_tracking)
                if found_fallback:
                    print(f"[Zalo Scanner] Đã định vị thành công mã mốc {start_tracking} bằng cuộn dự phòng.")
                else:
                    print(f"[Zalo Scanner] Không tìm thấy mã mốc {start_tracking} trong DOM. Bắt đầu từ vị trí hiện tại.")
        elif direction == "down":
            print("[Zalo Scanner] Hướng quét xuôi và không có mã mốc. Đang tìm và định vị tin nhắn ghim...")
            resolved_tracking = await self.resolve_pinned_tracking()
            if resolved_tracking:
                print(f"[Zalo Scanner] Đã định vị tin nhắn ghim thành công. Bắt đầu quét từ mốc: {resolved_tracking}")
                start_tracking = resolved_tracking
                pinned_tracking = resolved_tracking
            else:
                print("[Zalo Scanner] Không tìm thấy mốc ghim hợp lệ. Bắt đầu quét từ vị trí hiện tại.")
        elif direction == "up":
            # If scanning upwards and no start_tracking, ensure we are starting from the very bottom/latest messages
            print("[Zalo Scanner] Hướng quét ngược: Cuộn xuống dưới cùng để bắt đầu...")
            await self.zalo_page.evaluate("""
                () => {
                    const scrollContainer = document.querySelector(window.zalo_scroll_container || '.transform-gpu') || Array.from(document.querySelectorAll('div')).reduce(function(best,el){var s=window.getComputedStyle(el),r=el.getBoundingClientRect();if((s.overflowY==='scroll'||s.overflowY==='auto')&&r.height>400&&r.width>400&&el.scrollHeight>el.clientHeight+100){if(!best||el.scrollHeight>best.scrollHeight)return el;}return best;},null);
                    if (scrollContainer) {
                        scrollContainer.scrollTop = scrollContainer.scrollHeight;
                        scrollContainer.dispatchEvent(new Event('scroll', { bubbles: true }));
                        scrollContainer.dispatchEvent(new WheelEvent('wheel', { deltaY: 1000, bubbles: true }));
                    }
                }
            """)
            await asyncio.sleep(1.5)
            
        # JS code to run in Zalo Web to extract message history using precise bubble-based grouping
        js_scraper = r"""
        (args) => {
            const pinnedTrk = args ? args.pinnedTrk : null;
            const direction = args ? args.direction || 'down' : 'down';
            const startTrk = args ? args.startTrk : null;
            const allMsgItems = Array.from(document.querySelectorAll(window.zalo_chat_item || '.chat-item'));
            
            let pinnedIdx = -1;
            if (pinnedTrk) {
                pinnedIdx = allMsgItems.findIndex(item => (item.innerText || '').includes(pinnedTrk));
            }
            
            let startIdx = -1;
            if (startTrk) {
                startIdx = allMsgItems.findIndex(item => (item.innerText || '').includes(startTrk));
            }
            
            const hasReaction = (item) => {
                const v2space = item.querySelector(window.zalo_reaction_space || '.message-reaction-v2-space');
                if (v2space) {
                    const rect = v2space.getBoundingClientRect();
                    if (rect.height > 0) return true;
                }
                return false;
            };

            const getImagesInItem = (item) => {
                const imgs = Array.from(item.querySelectorAll('img'));
                const urls = [];
                imgs.forEach(img => {
                    const rect = img.getBoundingClientRect();
                    const src = (img.getAttribute('src') || img.src || '').toLowerCase();
                    const className = (img.className || '').toLowerCase();
                    if (
                        className.includes('avatar') || src.includes('avatar') || 
                        className.includes('logo') || src.includes('logo') || 
                        className.includes('emoji') || src.includes('emoji') ||
                        className.includes('sticker') || src.includes('sticker')
                    ) return;
                    if (rect.width > 30 || rect.height > 30 || img.naturalWidth > 30) {
                        const url = img.getAttribute('data-src') || img.src || '';
                        if (url) urls.push(url);
                    }
                });
                return urls;
            };

            const getVideosInItem = (item) => {
                const videos = [];
                const seenVideoCoords = new Set();
                const allElements = Array.from(item.querySelectorAll('*'));
                
                allElements.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 20 && rect.height > 20) {
                        const classStr = String(el.className && typeof el.className === 'object' ? el.className.baseVal || '' : el.className || '').toLowerCase();
                        const text = (el.textContent || '').trim();
                        const tagName = el.tagName.toLowerCase();
                        
                        const isVideoTag = tagName === 'video';
                        const isDurationPattern = /^\d{1,2}:\d{2}(:\d{2})?$/.test(text);
                        const isMsgTime = classStr.includes('time') || classStr.includes('send-time');
                        const isDuration = isDurationPattern && !isMsgTime;
                        const hasVideoClass = (classStr.includes('play') && !classStr.includes('display')) || classStr.includes('video') || classStr.includes('duration');
                        
                        if (isVideoTag || isDuration || hasVideoClass) {
                            let container = el;
                            let foundContainer = false;
                            
                            const elClass = String(el.className && typeof el.className === 'object' ? el.className.baseVal || '' : el.className || '').toLowerCase();
                            if (elClass.includes('card--group-photo__row__item') || elClass.includes('album__item') || (elClass.includes('video-message') && !elClass.includes('duration')) || (elClass.includes('video') && !elClass.includes('chat-item') && !elClass.includes('msg-item') && !elClass.includes('duration'))) {
                                foundContainer = true;
                            }
                            
                            if (!foundContainer) {
                                let p = el.parentElement;
                                for (let d = 0; d < 5 && p; d++) {
                                    const pClass = String(p.className && typeof p.className === 'object' ? p.className.baseVal || '' : p.className || '').toLowerCase();
                                    if (pClass.includes('card--group-photo__row__item') || pClass.includes('album__item') || (pClass.includes('video-message') && !pClass.includes('duration')) || (pClass.includes('video') && !pClass.includes('chat-item') && !pClass.includes('msg-item') && !pClass.includes('duration'))) {
                                        container = p;
                                        foundContainer = true;
                                        break;
                                    }
                                    p = p.parentElement;
                                }
                            }
                            
                            if (!foundContainer) {
                                let p2 = el.parentElement;
                                for (let d = 0; d < 4 && p2; d++) {
                                    const p2Class = String(p2.className && typeof p2.className === 'object' ? p2.className.baseVal || '' : p2.className || '').toLowerCase();
                                    if (p2.querySelector('img')) {
                                        container = p2;
                                        foundContainer = true;
                                        break;
                                    }
                                    if (p2Class.includes('chat-item') || p2Class.includes('msg-item')) break;
                                    p2 = p2.parentElement;
                                }
                            }
                            const hasImg = container.querySelector('img') !== null;
                            const hasBg = container.style.backgroundImage && container.style.backgroundImage !== 'none';
                            
                            if (isVideoTag || foundContainer || hasImg || hasBg) {
                                const cRect = container.getBoundingClientRect();
                                const cx = Math.round(cRect.left);
                                const cy = Math.round(cRect.top + window.scrollY);
                                const coordKey = `${cx}_${cy}`;
                                
                                if (!seenVideoCoords.has(coordKey)) {
                                    seenVideoCoords.add(coordKey);
                                    let url = '';
                                    const img = container.querySelector('img');
                                    if (img) {
                                        url = img.getAttribute('data-src') || img.src || '';
                                    } else {
                                        const bg = container.style.backgroundImage || window.getComputedStyle(container).backgroundImage;
                                        if (bg && bg !== 'none') {
                                            const match = bg.match(/url\(["']?(.*?)["']?\)/);
                                            if (match) url = match[1];
                                        }
                                    }
                                    if (!url && isVideoTag) {
                                        url = container.src || container.getAttribute('src') || '';
                                    }
                                    if (!url) {
                                        if (isDurationPattern && !hasImg && !hasBg) return;
                                        url = 'placeholder_video_url';
                                    }
                                    videos.push(url);
                                }
                            }
                        }
                    }
                });
                return videos;
            };

            const isRecalled = (item) => {
                const text = item.innerText || '';
                return text.includes('Đã thu hồi') || text.includes('tin nhắn bị xóa');
            };

            // 1. Identify senders
            let currentSender = null;
            allMsgItems.forEach(item => {
                const avatarImg = Array.from(item.querySelectorAll('img[class*="avatar"], .zavatar img, img[src*="ava"], img[src*="zadn.vn/"]')).find(img => {
                    const parentReact = img.closest('.message-reaction-container, .reacts-list, .reacts-container, [class*="react"]');
                    if (parentReact) return false;
                    const className = (img.className || '').toLowerCase();
                    if (className.includes('react') || className.includes('emoji') || className.includes('like') || className.includes('thumb')) return false;
                    return true;
                });
                if (avatarImg && avatarImg.src) {
                    currentSender = avatarImg.src;
                } else if (item.querySelector('.card--send, .card-send, .msg-send, .message-me, .me, [class*="owner"]')) {
                    currentSender = "self";
                }
                item.sender = currentSender || "unknown";
            });

            // 2. Find Anchors
            const textBubbles = [];
            allMsgItems.forEach((item, idx) => {
                if (pinnedIdx !== -1 && idx < pinnedIdx) return;
                const text = item.innerText || '';
                const matches = text.match(/\b\d{11,12}\b/g) || [];
                const trackingPatterns = text.match(/(?:Mã vận đơn|tracking|mã đơn)\s*:?\s*(\d{11,12})\b/gi) || [];
                const allTrackings = [...new Set([...matches, ...trackingPatterns.map(p => p.match(/\d{11,12}/)).filter(m => m).map(m => m[0])])];
                if (allTrackings.length > 0) {
                    const weightRegex = /\b(\d+(?:[.,]\d+)?)\s*[kK]?[gG]?\b/g;
                    const weightMatches = text.match(weightRegex) || [];
                    let weight = null;
                    for (let w of weightMatches) {
                        const numStr = w.replace(/[kKgG\s]/g, '').replace(',', '.');
                        if (!allTrackings.includes(numStr)) {
                            weight = parseFloat(numStr);
                            break;
                        }
                    }
                    textBubbles.push({
                        idx: idx,
                        trackingNumbers: allTrackings,
                        weight: weight,
                        images: [],
                        videos: [],
                        assignedMediaIndices: [],
                        hasReaction: hasReaction(item),
                        sender: item.sender
                    });
                }
            });

            // 3. Classify and Group Media utilizing dedicated functions for messy cases
            const classifyCase = (anchorIdx) => {
                const anchorItem = allMsgItems[anchorIdx];
                const sender = anchorItem.sender;
                
                const bubblesBefore = [];
                for (let i = anchorIdx - 1; i >= Math.max(0, anchorIdx - 5); i--) {
                    const it = allMsgItems[i];
                    if (isRecalled(it)) {
                        bubblesBefore.unshift({ idx: i, isRecalled: true, isMedia: false, isAnchor: false, images: [], videos: [] });
                        continue;
                    }
                    const text = it.innerText || '';
                    const matches = text.match(/\b\d{11,12}\b/g) || [];
                    if (matches.length > 0) break; // Don't cross another tracking number
                    if (it.sender !== sender) break; // Don't cross another sender
                    
                    const imgs = getImagesInItem(it);
                    const vids = getVideosInItem(it);
                    if (imgs.length > 0 || vids.length > 0) {
                        bubblesBefore.unshift({
                            idx: i,
                            isRecalled: false,
                            isMedia: true,
                            isAnchor: false,
                            images: imgs.filter(url => !vids.includes(url)),
                            videos: vids
                        });
                    }
                }
                
                const bubblesAfter = [];
                for (let i = anchorIdx + 1; i < Math.min(allMsgItems.length, anchorIdx + 6); i++) {
                    const it = allMsgItems[i];
                    if (isRecalled(it)) {
                        bubblesAfter.push({ idx: i, isRecalled: true, isMedia: false, isAnchor: false, images: [], videos: [] });
                        continue;
                    }
                    const text = it.innerText || '';
                    const matches = text.match(/\b\d{11,12}\b/g) || [];
                    if (matches.length > 0) break; // Don't cross another tracking number
                    if (it.sender !== sender) break; // Don't cross another sender
                    
                    const imgs = getImagesInItem(it);
                    const vids = getVideosInItem(it);
                    if (imgs.length > 0 || vids.length > 0) {
                        bubblesAfter.push({
                            idx: i,
                            isRecalled: false,
                            isMedia: true,
                            isAnchor: false,
                            images: imgs.filter(url => !vids.includes(url)),
                            videos: vids
                        });
                    }
                }
                
                const allImages = [];
                const allVideos = [];
                bubblesBefore.forEach(b => {
                    if (b.isMedia) {
                        allImages.push(...b.images);
                        allVideos.push(...b.videos);
                    }
                });
                bubblesAfter.forEach(b => {
                    if (b.isMedia) {
                        allImages.push(...b.images);
                        allVideos.push(...b.videos);
                    }
                });
                
                const uniqueImages = [...new Set(allImages)];
                const uniqueVideos = [...new Set(allVideos)];
                
                const mediaBefore = bubblesBefore.filter(b => b.isMedia);
                const mediaAfter = bubblesAfter.filter(b => b.isMedia);
                
                // Define 5 separate handlers for messy packages
                const processCase1 = (before, after, skipAfter = false) => {
                    const imgs = [];
                    const vids = [];
                    const indices = [];
                    before.forEach(b => {
                        if (b.isMedia) {
                            imgs.push(...b.images);
                            vids.push(...b.videos);
                            indices.push(b.idx);
                        }
                    });
                    if (!skipAfter) {
                        after.forEach(b => {
                            if (b.isMedia) {
                                imgs.push(...b.images);
                                vids.push(...b.videos);
                                indices.push(b.idx);
                            }
                        });
                    }
                    return {
                        caseType: "Trường hợp 1",
                        caseDescription: "Tách rời Video & Album ảnh",
                        assignedMediaIndices: indices,
                        images: [...new Set(imgs)],
                        videos: [...new Set(vids)]
                    };
                };

                const processCase2 = (before, after, skipAfter = false) => {
                    const imgs = [];
                    const vids = [];
                    const indices = [];
                    before.forEach(b => {
                        if (b.isMedia) {
                            imgs.push(...b.images);
                            vids.push(...b.videos);
                            indices.push(b.idx);
                        }
                    });
                    if (!skipAfter) {
                        after.forEach(b => {
                            if (b.isMedia) {
                                imgs.push(...b.images);
                                vids.push(...b.videos);
                                indices.push(b.idx);
                            }
                        });
                    }
                    return {
                        caseType: "Trường hợp 2",
                        caseDescription: "Có tin nhắn đã thu hồi trong Album + Ảnh lẻ",
                        assignedMediaIndices: indices,
                        images: [...new Set(imgs)],
                        videos: [...new Set(vids)]
                    };
                };

                const processCase3 = (before, after, skipAfter = false) => {
                    const imgs = [];
                    const vids = [];
                    const indices = [];
                    before.forEach(b => {
                        if (b.isMedia) {
                            imgs.push(...b.images);
                            vids.push(...b.videos);
                            indices.push(b.idx);
                        }
                    });
                    if (!skipAfter) {
                        after.forEach(b => {
                            if (b.isMedia) {
                                imgs.push(...b.images);
                                vids.push(...b.videos);
                                indices.push(b.idx);
                            }
                        });
                    }
                    return {
                        caseType: "Trường hợp 3",
                        caseDescription: "Media bị chia nhỏ cực đoan",
                        assignedMediaIndices: indices,
                        images: [...new Set(imgs)],
                        videos: [...new Set(vids)]
                    };
                };

                const processCase4 = (before, after, skipAfter = false) => {
                    const imgs = [];
                    const vids = [];
                    const indices = [];
                    before.forEach(b => {
                        if (b.isMedia) {
                            imgs.push(...b.images);
                            vids.push(...b.videos);
                            indices.push(b.idx);
                        }
                    });
                    if (!skipAfter) {
                        after.forEach(b => {
                            if (b.isMedia) {
                                imgs.push(...b.images);
                                vids.push(...b.videos);
                                indices.push(b.idx);
                            }
                        });
                    }
                    return {
                        caseType: "Trường hợp 4",
                        caseDescription: "Kẹp bánh mì (Media nằm cả trước và sau chữ)",
                        assignedMediaIndices: indices,
                        images: [...new Set(imgs)],
                        videos: [...new Set(vids)]
                    };
                };

                const processCase5 = (before, after, skipAfter = false) => {
                    const imgs = [];
                    const vids = [];
                    const indices = [];
                    before.forEach(b => {
                        if (b.isMedia && b.images.length > 0) {
                            imgs.push(...b.images);
                            indices.push(b.idx);
                        }
                    });
                    if (!skipAfter) {
                        after.forEach(b => {
                            if (b.isMedia && b.videos.length > 0) {
                                vids.push(...b.videos);
                                indices.push(b.idx);
                            }
                        });
                    }
                    return {
                        caseType: "Trường hợp 5",
                        caseDescription: "Ảnh trước, Video sau chữ",
                        assignedMediaIndices: indices,
                        images: [...new Set(imgs)],
                        videos: [...new Set(vids)]
                    };
                };

                const processStandard = (before, after, skipAfter = false) => {
                    const imgs = [];
                    const vids = [];
                    const indices = [];
                    before.forEach(b => {
                        if (b.isMedia) {
                            imgs.push(...b.images);
                            vids.push(...b.videos);
                            indices.push(b.idx);
                        }
                    });
                    if (!skipAfter) {
                        after.forEach(b => {
                            if (b.isMedia) {
                                imgs.push(...b.images);
                                vids.push(...b.videos);
                                indices.push(b.idx);
                            }
                        });
                    }
                    return {
                        caseType: "Chuẩn",
                        caseDescription: "Gửi chuẩn (1 album hoặc 1 cụm media duy nhất)",
                        assignedMediaIndices: indices,
                        images: [...new Set(imgs)],
                        videos: [...new Set(vids)]
                    };
                };

                const processKhac = (before, after, skipAfter = false) => {
                    const imgs = [];
                    const vids = [];
                    const indices = [];
                    before.forEach(b => {
                        if (b.isMedia) {
                            imgs.push(...b.images);
                            vids.push(...b.videos);
                            indices.push(b.idx);
                        }
                    });
                    if (!skipAfter) {
                        after.forEach(b => {
                            if (b.isMedia) {
                                imgs.push(...b.images);
                                vids.push(...b.videos);
                                indices.push(b.idx);
                            }
                        });
                    }
                    return {
                        caseType: "Khác",
                        caseDescription: "Lộn xộn tự do",
                        assignedMediaIndices: indices,
                        images: [...new Set(imgs)],
                        videos: [...new Set(vids)]
                    };
                };
                
                // Case 5: Album/images before anchor, video bubble after anchor
                const isCase5 = () => {
                    const hasImagesBeforeOnly = mediaBefore.some(b => b.images.length > 0 && b.videos.length === 0);
                    const hasVideosAfterOnly = mediaAfter.some(b => b.videos.length > 0 && b.images.length === 0);
                    const noVideoBefore = !mediaBefore.some(b => b.videos.length > 0);
                    const noImageAfter = !mediaAfter.some(b => b.images.length > 0);
                    return hasImagesBeforeOnly && hasVideosAfterOnly && noVideoBefore && noImageAfter;
                };
                
                // Case 4: Kẹp bánh mì (Media both before and after the text bubble)
                const isCase4 = () => {
                    return mediaBefore.length > 0 && mediaAfter.length > 0;
                };
                
                // Case 1: Tách rời Video & Album ảnh
                const isCase1 = () => {
                    if (mediaBefore.length >= 2 && mediaAfter.length === 0) {
                        const hasAlbum = mediaBefore.some(b => b.images.length >= 2);
                        const hasSeparateVideo = mediaBefore.some(b => b.videos.length > 0 && b.images.length === 0);
                        return hasAlbum && hasSeparateVideo;
                    }
                    if (mediaAfter.length >= 2 && mediaBefore.length === 0) {
                        const hasAlbum = mediaAfter.some(b => b.images.length >= 2);
                        const hasSeparateVideo = mediaAfter.some(b => b.videos.length > 0 && b.images.length === 0);
                        return hasAlbum && hasSeparateVideo;
                    }
                    return false;
                };
                
                // Case 2: Có tin nhắn đã thu hồi trong Album + Ảnh lẻ
                const isCase2 = () => {
                    const hasRecalledBefore = bubblesBefore.some(b => b.isRecalled);
                    const hasRecalledAfter = bubblesAfter.some(b => b.isRecalled);
                    return (hasRecalledBefore || hasRecalledAfter) && (uniqueImages.length > 0 || uniqueVideos.length > 0);
                };
                
                // Case 3: Media bị chia nhỏ cực đoan
                const isCase3 = () => {
                    const totalMediaBubbles = mediaBefore.length + mediaAfter.length;
                    return totalMediaBubbles >= 3;
                };
                
                // Standard Case
                const isStandard = () => {
                    const totalMediaBubbles = mediaBefore.length + mediaAfter.length;
                    return totalMediaBubbles === 1;
                };
                
                if (isCase2()) {
                    return processCase2(bubblesBefore, bubblesAfter);
                } else if (isCase3()) {
                    return processCase3(bubblesBefore, bubblesAfter);
                } else if (isCase5()) {
                    return processCase5(bubblesBefore, bubblesAfter);
                } else if (isCase4()) {
                    return processCase4(bubblesBefore, bubblesAfter);
                } else if (isCase1()) {
                    return processCase1(bubblesBefore, bubblesAfter);
                } else if (isStandard()) {
                    return processStandard(bubblesBefore, bubblesAfter);
                } else if (uniqueImages.length > 0 || uniqueVideos.length > 0) {
                    return processKhac(bubblesBefore, bubblesAfter);
                } else {
                    return {
                        caseType: "Không xác định",
                        caseDescription: "Không khớp các mẫu nhận dạng",
                        assignedMediaIndices: [],
                        images: [],
                        videos: []
                    };
                }
            };

            textBubbles.forEach(tb => {
                const res = classifyCase(tb.idx);
                tb.caseType = res.caseType;
                tb.caseDescription = res.caseDescription;
                tb.assignedMediaIndices = res.assignedMediaIndices;
                tb.images = res.images;
                tb.videos = res.videos;
            });

            // Determine stop boundaries
            let stopScan = false;
            let reactionIdx = -1;
            
            const isTextBubble = (idx) => {
                for (const tb of textBubbles) {
                    if (tb.idx === idx) return true;
                }
                return false;
            };

            if (direction === 'up') {
                for (let i = allMsgItems.length - 1; i >= 0; i--) {
                    if (startIdx !== -1 && i >= startIdx) continue;
                    if (hasReaction(allMsgItems[i]) && isTextBubble(i)) {
                        reactionIdx = i;
                        stopScan = true;
                        break;
                    }
                }
            } else if (direction === 'down') {
                for (let i = 0; i < allMsgItems.length; i++) {
                    if (startIdx !== -1 && i <= startIdx) continue;
                    if (hasReaction(allMsgItems[i]) && isTextBubble(i)) {
                        reactionIdx = i;
                        stopScan = true;
                        break;
                    }
                }
            }

            const viewPackages = [];
            textBubbles.forEach(text => {
                if (pinnedIdx !== -1 && text.idx < pinnedIdx) return;
                if (startIdx !== -1) {
                    if (direction === 'up' && text.idx > startIdx) return;
                    if (direction === 'down' && text.idx < startIdx) return;
                }
                
                if (direction === 'up') {
                    if (reactionIdx !== -1 && text.idx <= reactionIdx) return;
                } else {
                    if (reactionIdx !== -1 && text.idx >= reactionIdx) return;
                }
                
                if (text.hasReaction) return;
                
                if (true) { // Capture all packages regardless of media rendering status during scan
                    text.trackingNumbers.forEach(trackingNumber => {
                        if (!viewPackages.some(p => p.trackingNumber === trackingNumber)) {
                            viewPackages.push({
                                trackingNumber,
                                weight: text.weight,
                                images: text.images,
                                videos: text.videos,
                                caseType: text.caseType,
                                caseDescription: text.caseDescription
                            });
                        }
                    });
                }
            });
            
            return {
                packages: viewPackages,
                stopScan: stopScan
            };
        }
        """
        
        accumulated_packages = {}
        last_scroll_top = -1
        last_scroll_height = -1
        limit_retry_count = 0
        max_limit_retries = 5
        first_scan = True
        
        # Clear debug log at start of scan
        if first_scan:
            try:
                os.makedirs("data", exist_ok=True)
                with open("data/debug_scan.log", "w", encoding="utf-8") as log_f:
                    log_f.write(f"=== New Scan Started: direction={direction}, start_tracking={start_tracking} ===\n")
            except Exception:
                pass

        # Thực hiện cuộn và quét tối đa 300 bước để tránh dừng giữa chừng khi có hàng trăm đơn hàng
        for step in range(300):
            scroll_info = await self.zalo_page.evaluate("""
                () => {
                    const scrollContainer = document.querySelector(window.zalo_scroll_container || '.transform-gpu') ||
                        Array.from(document.querySelectorAll('div')).reduce((b,el) => {
                            const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
                            if ((s.overflowY==='scroll'||s.overflowY==='auto') && r.height>400 && r.width>400 && el.scrollHeight>el.clientHeight+100) {
                                if (!b || el.scrollHeight > b.scrollHeight) return el;
                            }
                            return b;
                        }, null);
                    if (!scrollContainer) return null;
                    return {
                        scrollTop: scrollContainer.scrollTop,
                        scrollHeight: scrollContainer.scrollHeight,
                        clientHeight: scrollContainer.clientHeight
                    };
                }
            """)
            
            if not scroll_info:
                print("[Zalo Scanner] Không tìm thấy khung cuộn chat để cuộn.")
                break
                
            current_scroll_top = scroll_info["scrollTop"]
            current_scroll_height = scroll_info["scrollHeight"]
            current_client_height = scroll_info["clientHeight"]
            
            # Boundary limit check depending on direction
            if direction == "up":
                is_limit = current_scroll_top <= 2
            else:
                is_limit = current_scroll_top + current_client_height >= current_scroll_height - 15
            if is_limit:
                if not first_scan and current_scroll_height == last_scroll_height and current_scroll_top == last_scroll_top:
                    limit_retry_count += 1
                    print(f"[Zalo Scanner] Đang chờ Zalo Web tải thêm tin nhắn/DOM boundary (Lần thử {limit_retry_count}/{max_limit_retries})...")
                    if limit_retry_count >= max_limit_retries:
                        print(f"[Zalo Scanner] Đã chạm giới hạn cuộc trò chuyện (scrollTop: {current_scroll_top}).")
                        break
                    await asyncio.sleep(0.8)
                else:
                    limit_retry_count = 0
            else:
                limit_retry_count = 0
            
            last_scroll_top = current_scroll_top
            last_scroll_height = current_scroll_height
            
            # Ở bước quét đầu tiên, nếu phát hiện có mã ghim, chỉ lấy các đơn hàng sau tin nhắn ghim đó
            # Ở các bước sau, quét toàn bộ tin nhắn hiện có trong DOM ở viewport hiện tại
            param_trk = pinned_tracking if (first_scan and pinned_tracking) else None
            
            eval_res = await self.zalo_page.evaluate(js_scraper, {"pinnedTrk": param_trk, "direction": direction, "startTrk": start_tracking})
            if isinstance(eval_res, dict) and "error" in eval_res:
                raise Exception(eval_res["error"])
                
            # Log diagnostics
            try:
                with open("data/debug_scan.log", "a", encoding="utf-8") as log_f:
                    log_f.write(f"\n--- Step {step} | direction: {direction} | start_tracking: {start_tracking} ---\n")
                    if eval_res and "debug" in eval_res:
                        log_f.write(json.dumps(eval_res["debug"], ensure_ascii=False, indent=2) + "\n")
                    else:
                        log_f.write("No debug info returned from JS\n")
            except Exception as e_log:
                print(f"Lỗi ghi log debug: {e_log}")

            scanned_packages = eval_res.get("packages", []) if eval_res else []
            stop_scan_now = eval_res.get("stopScan", False) if eval_res else False
            
            new_count = 0
            merged_count = 0
            for pkg in scanned_packages:
                trk = pkg["trackingNumber"]
                if pkg.get("caseType") and pkg.get("caseType") not in ["Chuẩn", "Không xác định"]:
                    self.learn_messy_package(pkg)
                if trk in accumulated_packages:
                    existing = accumulated_packages[trk]
                    # Cập nhật cân nặng nếu có
                    if pkg.get("weight") is not None:
                        existing["weight"] = pkg["weight"]
                    
                    # Gộp ảnh minh chứng (loại bỏ trùng lặp)
                    merged_images = existing["images"][:]
                    for img in pkg["images"]:
                        if img not in merged_images:
                            merged_images.append(img)
                    existing["images"] = merged_images
                    
                    # Gộp video minh chứng (loại bỏ trùng lặp)
                    merged_videos = existing["videos"][:]
                    for vid in pkg["videos"]:
                        if vid not in merged_videos:
                            merged_videos.append(vid)
                    existing["videos"] = merged_videos
                    
                    # Cập nhật thông tin case
                    if pkg.get("caseType"):
                        existing["caseType"] = pkg["caseType"]
                        existing["caseDescription"] = pkg["caseDescription"]
                    merged_count += 1
                else:
                    accumulated_packages[trk] = pkg
                    new_count += 1
                    
            print(f"[Zalo Scanner] Hướng {direction} - Bước {step+1}: Quét được {len(scanned_packages)} đơn. Lũy kế: {len(accumulated_packages)} (Thêm mới: {new_count}, Gộp: {merged_count})")
            
            if stop_scan_now:
                print(f"[Zalo Scanner] Phát hiện tin nhắn đã có Tim/Like (biên giới xử lý). Dừng quét.")
                break
                
            # Scroll
            await self.zalo_page.evaluate("""
                (dir) => {
                    const sc = document.querySelector(window.zalo_scroll_container || '.transform-gpu') ||
                        Array.from(document.querySelectorAll('div')).reduce((b,el) => {
                            const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
                            if ((s.overflowY==='scroll'||s.overflowY==='auto') && r.height>400 && r.width>400 && el.scrollHeight>el.clientHeight+100) {
                                if (!b || el.scrollHeight > b.scrollHeight) return el;
                            }
                            return b;
                        }, null);
                    if (sc) {
                        if (dir === 'up') {
                            sc.scrollTop -= 1000;
                        } else {
                            sc.scrollTop += 600;
                        }
                    }
                }
            """, direction)
            
            first_scan = False
            # Chờ 250ms để trình duyệt tải và render thêm tin nhắn mới vào DOM
            await asyncio.sleep(0.25)
            
        return list(accumulated_packages.values())


    async def scroll_zalo(self, times):
        status = await self.get_status()
        if status["zalo"] == "disconnected":
            raise Exception("Chưa mở hoặc chưa kết nối được tab Zalo Web!")

        await self.zalo_page.bring_to_front()
        
        js_scroll = """
        async (times) => {
            // Find scroll container of chat views
            const scrollContainer = document.querySelector('.message-view__scroll .transform-gpu, #messageViewContainer .transform-gpu, .transform-gpu');
            if (!scrollContainer) {
                return { success: false, error: 'Không tìm thấy khung cuộn chat Zalo. Hãy chọn một cuộc trò chuyện.' };
            }
            
            for (let i = 0; i < times; i++) {
                scrollContainer.scrollTop = 0;
                // Wait for Zalo to load new items
                await new Promise(resolve => setTimeout(resolve, 800));
            }
            return { success: true };
        }
        """
        result = await self.zalo_page.evaluate(js_scroll, times)
        if result and not result.get("success"):
            raise Exception(result.get("error"))
            
        return True

    async def perform_ocr_space(self, image_path, api_key="helloworld"):
        """Performs OCR on the image using OCR.space API."""
        url = "https://api.ocr.space/parse/image"
        payload = {
            'apikey': api_key,
            'language': 'eng',
            'isOverlayRequired': False,
            'detectOrientation': True,
            'scale': True,
            'OCREngine': 2
        }
        
        loop = asyncio.get_running_loop()
        def do_post():
            try:
                with open(image_path, 'rb') as f:
                    files = {'image': f}
                    return requests.post(url, files=files, data=payload, timeout=20)
            except Exception as e:
                print(f"[OCR Space Helper] Exception in requests post: {e}")
                return None
                
        try:
            response = await loop.run_in_executor(None, do_post)
            if response and response.status_code == 200:
                result = response.json()
                if result.get("IsErroredOnProcessing"):
                    print(f"[OCR Space Helper] Error: {result.get('ErrorMessage')}")
                    return None
                parsed_results = result.get("ParsedResults", [])
                if parsed_results:
                    return parsed_results[0].get("ParsedText", "")
            elif response:
                print(f"[OCR Space Helper] Error response {response.status_code}: {response.text}")
        except Exception as e:
            print(f"[OCR Space Helper] Exception: {e}")
        return None

    def read_barcode_from_image(self, image_path):
        """Reads barcodes from an image using zxing-cpp."""
        try:
            img = cv2.imread(image_path)
            if img is None:
                return []
            results = zxingcpp.read_barcodes(img)
            return [res.text for res in results]
        except Exception as e:
            print(f"[Barcode Reader] Error reading {image_path}: {e}")
            return []

    def get_all_scanned_tracking_numbers(self):
        """Reads scanned_packages.json to return a set of all valid scanned tracking numbers."""
        scanned_path = os.path.join(DATA_DIR, "scanned_packages.json")
        trackings = set()
        if os.path.exists(scanned_path):
            try:
                with open(scanned_path, "r", encoding="utf-8") as f:
                    pkgs = json.load(f)
                    for p in pkgs:
                        if p.get("trackingNumber"):
                            trackings.add(str(p["trackingNumber"]).strip())
            except Exception as e:
                print(f"[OCR Helper] Error loading scanned packages: {e}")
        return trackings

    def find_folder_for_tracking(self, tracking_number):
        """Finds the folder name (index or raw number) for a tracking number."""
        scanned_path = os.path.join(DATA_DIR, "scanned_packages.json")
        if os.path.exists(scanned_path):
            try:
                with open(scanned_path, "r", encoding="utf-8") as f:
                    pkgs = json.load(f)
                    for p in pkgs:
                        if p.get("trackingNumber") == tracking_number:
                            folder_name = p.get("folderName")
                            if folder_name:
                                return str(folder_name)
            except Exception as e:
                print(f"[OCR Helper] Error searching scanned packages: {e}")
                
        # Check folders on disk as fallback
        if os.path.exists(DATA_DIR):
            for item in os.listdir(DATA_DIR):
                item_path = os.path.join(DATA_DIR, item)
                if os.path.isdir(item_path):
                    if os.path.exists(os.path.join(item_path, f"{tracking_number}.txt")):
                        return item
        return tracking_number

    def add_temp_image_to_folder(self, folder_path, src_image_path):
        """Moves a mismatched image to its correct folder as a temp file and reorganizes the folder."""
        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)
            
        # 1. Rename existing image_*.jpg and video_*.mp4 back to temp format
        for i in range(1, 10):
            p = os.path.join(folder_path, f"image_{i}.jpg")
            if os.path.exists(p):
                temp_p = os.path.join(folder_path, f"image_temp_existing_{i}_{int(time.time())}.jpg")
                try:
                    if os.path.exists(temp_p):
                        os.remove(temp_p)
                    os.rename(p, temp_p)
                except Exception as e:
                    print(f"[OCR Reorganizer] Error renaming image {p}: {e}")
                    
        p_vid = os.path.join(folder_path, "video_1.mp4")
        if os.path.exists(p_vid):
            temp_vid = os.path.join(folder_path, f"video_temp_existing_1_{int(time.time())}.mp4")
            try:
                if os.path.exists(temp_vid):
                    os.remove(temp_vid)
                os.rename(p_vid, temp_vid)
            except Exception as e:
                print(f"[OCR Reorganizer] Error renaming video {p_vid}: {e}")
                
        # 2. Copy the mismatched image to the folder as a temp file
        dest_name = f"image_temp_ocr_moved_{int(time.time())}.jpg"
        dest_path = os.path.join(folder_path, dest_name)
        try:
            shutil.copy2(src_image_path, dest_path)
            print(f"[OCR Reorganizer] Copied {src_image_path} -> {dest_path}")
        except Exception as e:
            print(f"[OCR Reorganizer] Error copying file: {e}")
            return
            
        # 3. Read and sort all temp files
        temp_images = []
        temp_videos = []
        for f in os.listdir(folder_path):
            full_p = os.path.join(folder_path, f)
            if os.path.isfile(full_p):
                if f.startswith("image_temp_"):
                    temp_images.append(full_p)
                elif f.startswith("video_temp_"):
                    temp_videos.append(full_p)
                    
        temp_images.sort()
        temp_videos.sort()
        
        # 4. Clean up any remaining non-temp media files to avoid conflicts
        for f in os.listdir(folder_path):
            if (f.startswith("image_") or f.startswith("video_")) and not (f.startswith("image_temp_") or f.startswith("video_temp_")):
                try:
                    os.remove(os.path.join(folder_path, f))
                except Exception:
                    pass
                    
        # 5. Rename first 3 images and first video to final names
        for idx, temp_p in enumerate(temp_images[:3]):
            target_p = os.path.join(folder_path, f"image_{idx+1}.jpg")
            try:
                if os.path.exists(target_p):
                    os.remove(target_p)
                os.rename(temp_p, target_p)
            except Exception as e:
                print(f"[OCR Reorganizer] Error creating final image: {e}")
                
        for idx, temp_p in enumerate(temp_videos[:1]):
            target_p = os.path.join(folder_path, f"video_{idx+1}.mp4")
            try:
                if os.path.exists(target_p):
                    os.remove(target_p)
                os.rename(temp_p, target_p)
            except Exception as e:
                print(f"[OCR Reorganizer] Error creating final video: {e}")
                
        # 6. Clean up left-over temp files
        for f in os.listdir(folder_path):
            if f.startswith("image_temp_") or f.startswith("video_temp_"):
                try:
                    os.remove(os.path.join(folder_path, f))
                except Exception:
                    pass

        # 7. Update scanned_packages.json to reflect the new image path for the target package
        scanned_path = os.path.join(DATA_DIR, "scanned_packages.json")
        if os.path.exists(scanned_path):
            try:
                folder_name = os.path.basename(folder_path)
                final_imgs = []
                for f in sorted(os.listdir(folder_path)):
                    if f.startswith("image_") and f.lower().endswith(".jpg") and not f.startswith("image_temp_"):
                        final_imgs.append(f"/data/{folder_name}/{f}")
                        
                from filelock import FileLock
                with FileLock(scanned_path + '.lock', timeout=5):
                    with open(scanned_path, "r", encoding="utf-8") as sf:
                        pkgs = json.load(sf)
                        
                    updated = False
                    for p in pkgs:
                        if p.get("folderName") == folder_name or p.get("trackingNumber") == folder_name:
                            p["images"] = final_imgs
                            p["localStatus"] = "Đã tải về"
                            updated = True
                            break
                            
                    if updated:
                        with open(scanned_path, "w", encoding="utf-8") as sf:
                            json.dump(pkgs, sf, ensure_ascii=False, indent=4)
                        print(f"[OCR Reorganizer] Updated scanned_packages.json images list for folder {folder_name} to: {final_imgs}")
            except Exception as e_json:
                print(f"[OCR Reorganizer] Error updating scanned_packages.json: {e_json}")

    def learn_messy_package(self, pkg):
        """Saves messy package patterns to learn_parkage.json in the config folder for smart learning."""
        try:
            case_type = pkg.get("caseType")
            if not case_type or case_type in ["Chuẩn", "Không xác định"]:
                return
                
            config_dir = os.path.abspath(os.path.join(DATA_DIR, "..", "config"))
            os.makedirs(config_dir, exist_ok=True)
            learn_file = os.path.join(config_dir, "learn_parkage.json")
            
            packages_list = []
            if os.path.exists(learn_file):
                try:
                    with open(learn_file, "r", encoding="utf-8") as f:
                        packages_list = json.load(f)
                except Exception:
                    packages_list = []
                        
            # Check if already exists
            exists = False
            for item in packages_list:
                if item.get("trackingNumber") == pkg["trackingNumber"]:
                    # Update case information
                    item["caseType"] = case_type
                    item["caseDescription"] = pkg.get("caseDescription", "")
                    item["weight"] = pkg.get("weight")
                    item["images_count"] = len(pkg.get("images", []))
                    item["videos_count"] = len(pkg.get("videos", []))
                    item["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                    exists = True
                    break
                    
            if not exists:
                packages_list.append({
                    "trackingNumber": pkg["trackingNumber"],
                    "weight": pkg.get("weight"),
                    "caseType": case_type,
                    "caseDescription": pkg.get("caseDescription", ""),
                    "images_count": len(pkg.get("images", [])),
                    "videos_count": len(pkg.get("videos", [])),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
                })
                
            with open(learn_file, "w", encoding="utf-8") as f:
                json.dump(packages_list, f, ensure_ascii=False, indent=4)
                
            print(f"[Learning Engine] Đã học và ghi nhận đơn hàng gửi lộn xộn: {pkg['trackingNumber']} ({case_type} - {pkg.get('caseDescription', '')})")
        except Exception as e:
            print(f"[Learning Engine] Lỗi khi lưu học đơn hàng: {e}")

    async def download_package_media(self, package, pkg_index=None, progress_callback=None, skip_banner_click=False, skip_scroll_search=False, reverse_scan=False):
        """Downloads all images and videos for a package using the Zalo tab context."""
        tracking_number = package["trackingNumber"]
        folder_name = str(pkg_index) if pkg_index is not None else tracking_number
        package_dir = os.path.join(DATA_DIR, folder_name)
        os.makedirs(package_dir, exist_ok=True)
        
        # Save weight & tracking info to a text file named after the tracking number for easy copying
        weight = package.get("weight")
        weight_str = f"{weight}" if weight is not None else "0"
        txt_path = os.path.join(package_dir, f"{tracking_number}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"{tracking_number}\n{weight_str}\n\nMã vận đơn: {tracking_number}\nCân nặng: {weight_str} kg\n")
            
        final_images = []
        final_videos = []
        
        # --- PHASE 1: Locate the tracking number and its associated media bubble(s) ---
        print(f"Bắt đầu định vị đơn hàng {tracking_number} trên Zalo...")
        if progress_callback:
            await progress_callback(f"Đang định vị mã vận đơn {tracking_number} trên Zalo...")
            
        clicked = False
        if not skip_banner_click:
            # Try to click the banner using Playwright first if it contains the tracking number
            banner_selectors = [
                '.list-chat-box-banner',
                '[class*="list-chat-box-banner"]',
                '.chat-group-topic',
                '[class*="pinned-message"]',
                '[class*="pinned"]',
                '[class*="pin"]',
                '[class*="announce"]',
                '[class*="board"]',
                '[class*="banner"]'
            ]
            for selector in banner_selectors:
                try:
                    locator = self.zalo_page.locator(selector).first
                    if await locator.is_visible() and await locator.bounding_box():
                        text = await locator.inner_text()
                        if tracking_number in text:
                            print(f"[Zalo Download] Clicking banner using Playwright locator: {selector}")
                            await locator.click(timeout=3000)
                            clicked = True
                            break
                except Exception as ex:
                    print(f"[Zalo Download] Error clicking banner with selector {selector}: {ex}")
            
            if clicked:
                # Wait for Zalo to scroll
                await asyncio.sleep(1.5)
            
        marker_result = await self.zalo_page.evaluate(r"""
            async ({ trackingNumber, skipScrollSearch, reverseScan }) => {
                try {
                    const scrollContainer = document.querySelector('.message-view__scroll .transform-gpu, #messageViewContainer .transform-gpu, .transform-gpu') || Array.from(document.querySelectorAll('div')).reduce(function(best,el){var s=window.getComputedStyle(el),r=el.getBoundingClientRect();if((s.overflowY==='scroll'||s.overflowY==='auto')&&r.height>400&&r.width>400&&el.scrollHeight>el.clientHeight+100){if(!best||el.scrollHeight>best.scrollHeight)return el;}return best;},null);
                    if (!scrollContainer) return { success: false, error: 'Không tìm thấy khung cuộn chat Zalo.' };
                    const allMsgItems = Array.from(document.querySelectorAll(window.zalo_chat_item || '.chat-item'));
                    let pinnedIdx = -1;
                    
                    const hasReaction = (item) => {
                        const v2space = item.querySelector(window.zalo_reaction_space || '.message-reaction-v2-space');
                        if (v2space) {
                            const rect = v2space.getBoundingClientRect();
                            if (rect.height > 0) return true;
                        }
                        return false;
                    };

                    const getImagesInItem = (item) => {
                        const imgs = Array.from(item.querySelectorAll('img'));
                        const urls = [];
                        imgs.forEach(img => {
                            const rect = img.getBoundingClientRect();
                            const src = (img.getAttribute('src') || img.src || '').toLowerCase();
                            const className = (img.className || '').toLowerCase();
                            if (
                                className.includes('avatar') || src.includes('avatar') || 
                                className.includes('logo') || src.includes('logo') || 
                                className.includes('emoji') || src.includes('emoji') ||
                                className.includes('sticker') || src.includes('sticker')
                            ) return;
                            if (rect.width > 30 || rect.height > 30 || img.naturalWidth > 30) {
                                const url = img.getAttribute('data-src') || img.src || '';
                                if (url) urls.push(url);
                            }
                        });
                        return urls;
                    };

                    const getVideosInItem = (item) => {
                        const videos = [];
                        const seenVideoCoords = new Set();
                        const allElements = Array.from(item.querySelectorAll('*'));
                        
                        allElements.forEach(el => {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 20 && rect.height > 20) {
                                const classStr = String(el.className && typeof el.className === 'object' ? el.className.baseVal || '' : el.className || '').toLowerCase();
                                const text = (el.textContent || '').trim();
                                const tagName = el.tagName.toLowerCase();
                                
                                const isVideoTag = tagName === 'video';
                                const isDurationPattern = /^\d{1,2}:\d{2}(:\d{2})?$/.test(text);
                                const isMsgTime = classStr.includes('time') || classStr.includes('send-time');
                                const isDuration = isDurationPattern && !isMsgTime;
                                const hasVideoClass = (classStr.includes('play') && !classStr.includes('display')) || classStr.includes('video') || classStr.includes('duration');
                                
                                if (isVideoTag || isDuration || hasVideoClass) {
                                    let container = el;
                                    let foundContainer = false;
                                    
                                    const elClass = String(el.className && typeof el.className === 'object' ? el.className.baseVal || '' : el.className || '').toLowerCase();
                                    if (elClass.includes('card--group-photo__row__item') || elClass.includes('album__item') || (elClass.includes('video-message') && !elClass.includes('duration')) || (elClass.includes('video') && !elClass.includes('chat-item') && !elClass.includes('msg-item') && !elClass.includes('duration'))) {
                                        foundContainer = true;
                                    }
                                    
                                    if (!foundContainer) {
                                        let p = el.parentElement;
                                        for (let d = 0; d < 5 && p; d++) {
                                            const pClass = String(p.className && typeof p.className === 'object' ? p.className.baseVal || '' : p.className || '').toLowerCase();
                                            if (pClass.includes('card--group-photo__row__item') || pClass.includes('album__item') || (pClass.includes('video-message') && !pClass.includes('duration')) || (pClass.includes('video') && !pClass.includes('chat-item') && !pClass.includes('msg-item') && !pClass.includes('duration'))) {
                                                container = p;
                                                foundContainer = true;
                                                break;
                                            }
                                            p = p.parentElement;
                                        }
                                    }
                                    
                                    if (!foundContainer) {
                                        let p2 = el.parentElement;
                                        for (let d = 0; d < 4 && p2; d++) {
                                            const p2Class = String(p2.className && typeof p2.className === 'object' ? p2.className.baseVal || '' : p2.className || '').toLowerCase();
                                            if (p2.querySelector('img')) {
                                                container = p2;
                                                foundContainer = true;
                                                break;
                                            }
                                            if (p2Class.includes('chat-item') || p2Class.includes('msg-item')) break;
                                            p2 = p2.parentElement;
                                        }
                                    }
                                    const hasImg = container.querySelector('img') !== null;
                                    const hasBg = container.style.backgroundImage && container.style.backgroundImage !== 'none';
                                    
                                    if (isVideoTag || foundContainer || hasImg || hasBg) {
                                        const cRect = container.getBoundingClientRect();
                                        const cx = Math.round(cRect.left);
                                        const cy = Math.round(cRect.top + window.scrollY);
                                        const coordKey = `${cx}_${cy}`;
                                        
                                        if (!seenVideoCoords.has(coordKey)) {
                                            seenVideoCoords.add(coordKey);
                                            let url = '';
                                            const img = container.querySelector('img');
                                            if (img) {
                                                url = img.getAttribute('data-src') || img.src || '';
                                            } else {
                                                const bg = container.style.backgroundImage || window.getComputedStyle(container).backgroundImage;
                                                if (bg && bg !== 'none') {
                                                    const match = bg.match(/url\(["']?(.*?)["']?\)/);
                                                    if (match) url = match[1];
                                                }
                                            }
                                            if (!url && isVideoTag) {
                                                url = container.src || container.getAttribute('src') || '';
                                            }
                                            if (!url) {
                                                if (isDurationPattern && !hasImg && !hasBg) return;
                                                url = 'placeholder_video_url';
                                            }
                                            videos.push(url);
                                        }
                                    }
                                }
                            }
                        });
                        return videos;
                    };

                    const isRecalled = (item) => {
                        const text = item.innerText || '';
                        return text.includes('Đã thu hồi') || text.includes('tin nhắn bị xóa');
                    };

                    // 1. Identify senders
                    allMsgItems.forEach(item => {
                        const className = (item.className && typeof item.className === 'string' ? item.className : '').toLowerCase();
                        const innerHTML = item.innerHTML || '';
                        if (className.includes('me') || className.includes('-send') || innerHTML.includes('card--send') || innerHTML.includes('message-me')) {
                            item.sender = "self";
                        } else {
                            item.sender = "them";
                        }
                    });

                    // 2. Find Anchors
                    const textBubbles = [];
                    allMsgItems.forEach((item, idx) => {
                        if (pinnedIdx !== -1 && idx < pinnedIdx) return;
                        const text = item.innerText || '';
                        const matches = text.match(/\b\d{11,12}\b/g) || [];
                        const trackingPatterns = text.match(/(?:Mã vận đơn|tracking|mã đơn)\s*:?\s*(\d{11,12})\b/gi) || [];
                        const allTrackings = [...new Set([...matches, ...trackingPatterns.map(p => p.match(/\d{11,12}/)).filter(m => m).map(m => m[0])])];
                        if (allTrackings.length > 0) {
                            const weightRegex = /\b(\d+(?:[.,]\d+)?)\s*[kK]?[gG]?\b/g;
                            const weightMatches = text.match(weightRegex) || [];
                            let weight = null;
                            for (let w of weightMatches) {
                                const numStr = w.replace(/[kKgG\s]/g, '').replace(',', '.');
                                if (!allTrackings.includes(numStr)) {
                                    weight = parseFloat(numStr);
                                    break;
                                }
                            }
                            textBubbles.push({
                                idx: idx,
                                trackingNumbers: allTrackings,
                                weight: weight,
                                images: [],
                                videos: [],
                                assignedMediaIndices: [],
                                hasReaction: hasReaction(item),
                                sender: item.sender
                            });
                        }
                    });

                    // 3. Classify and Group Media utilizing dedicated functions for messy cases
                    const classifyCase = (anchorIdx) => {
                        const anchorItem = allMsgItems[anchorIdx];
                        const sender = anchorItem.sender;
                        
                        const bubblesBefore = [];
                        for (let i = anchorIdx - 1; i >= Math.max(0, anchorIdx - 5); i--) {
                            const it = allMsgItems[i];
                            if (isRecalled(it)) {
                                bubblesBefore.unshift({ idx: i, isRecalled: true, isMedia: false, isAnchor: false, images: [], videos: [] });
                                continue;
                            }
                            const text = it.innerText || '';
                            const matches = text.match(/\b\d{11,12}\b/g) || [];
                            if (matches.length > 0) break;
                            if (it.sender !== sender) break;
                            
                            const imgs = getImagesInItem(it);
                            const vids = getVideosInItem(it);
                            if (imgs.length > 0 || vids.length > 0) {
                                bubblesBefore.unshift({
                                    idx: i,
                                    isRecalled: false,
                                    isMedia: true,
                                    isAnchor: false,
                                    images: imgs.filter(url => !vids.includes(url)),
                                    videos: vids
                                });
                            }
                        }
                        
                        const bubblesAfter = [];
                        for (let i = anchorIdx + 1; i < Math.min(allMsgItems.length, anchorIdx + 6); i++) {
                            const it = allMsgItems[i];
                            if (isRecalled(it)) {
                                bubblesAfter.push({ idx: i, isRecalled: true, isMedia: false, isAnchor: false, images: [], videos: [] });
                                continue;
                            }
                            const text = it.innerText || '';
                            const matches = text.match(/\b\d{11,12}\b/g) || [];
                            if (matches.length > 0) break;
                            if (it.sender !== sender) break;
                            
                            const imgs = getImagesInItem(it);
                            const vids = getVideosInItem(it);
                            if (imgs.length > 0 || vids.length > 0) {
                                bubblesAfter.push({
                                    idx: i,
                                    isRecalled: false,
                                    isMedia: true,
                                    isAnchor: false,
                                    images: imgs.filter(url => !vids.includes(url)),
                                    videos: vids
                                });
                            }
                        }
                        
                        const allImages = [];
                        const allVideos = [];
                        bubblesBefore.forEach(b => {
                            if (b.isMedia) {
                                allImages.push(...b.images);
                                allVideos.push(...b.videos);
                            }
                        });
                        
                        let skipAfter = false;
                        if (reverseScan) {
                            const uniqueImgBefore = [...new Set(allImages)];
                            const uniqueVidBefore = [...new Set(allVideos)];
                            if (uniqueImgBefore.length >= 3 && uniqueVidBefore.length >= 1) {
                                skipAfter = true;
                            }
                        }
                        
                        if (!skipAfter) {
                            bubblesAfter.forEach(b => {
                                if (b.isMedia) {
                                    allImages.push(...b.images);
                                    allVideos.push(...b.videos);
                                }
                            });
                        }
                        
                        const uniqueImages = [...new Set(allImages)];
                        const uniqueVideos = [...new Set(allVideos)];
                        
                        const mediaBefore = bubblesBefore.filter(b => b.isMedia);
                        const mediaAfter = bubblesAfter.filter(b => b.isMedia);
                        
                        // Define 5 separate handlers for messy packages
                        const processCase1 = (before, after, skipAfter = false) => {
                            const imgs = [];
                            const vids = [];
                            const indices = [];
                            before.forEach(b => {
                                if (b.isMedia) {
                                    imgs.push(...b.images);
                                    vids.push(...b.videos);
                                    indices.push(b.idx);
                                }
                            });
                            if (!skipAfter) {
                                after.forEach(b => {
                                    if (b.isMedia) {
                                        imgs.push(...b.images);
                                        vids.push(...b.videos);
                                        indices.push(b.idx);
                                    }
                                });
                            }
                            return {
                                caseType: "Trường hợp 1",
                                caseDescription: "Tách rời Video & Album ảnh",
                                assignedMediaIndices: indices,
                                images: [...new Set(imgs)],
                                videos: [...new Set(vids)]
                            };
                        };

                        const processCase2 = (before, after, skipAfter = false) => {
                            const imgs = [];
                            const vids = [];
                            const indices = [];
                            before.forEach(b => {
                                if (b.isMedia) {
                                    imgs.push(...b.images);
                                    vids.push(...b.videos);
                                    indices.push(b.idx);
                                }
                            });
                            if (!skipAfter) {
                                after.forEach(b => {
                                    if (b.isMedia) {
                                        imgs.push(...b.images);
                                        vids.push(...b.videos);
                                        indices.push(b.idx);
                                    }
                                });
                            }
                            return {
                                caseType: "Trường hợp 2",
                                caseDescription: "Có tin nhắn đã thu hồi trong Album + Ảnh lẻ",
                                assignedMediaIndices: indices,
                                images: [...new Set(imgs)],
                                videos: [...new Set(vids)]
                            };
                        };

                        const processCase3 = (before, after, skipAfter = false) => {
                            const imgs = [];
                            const vids = [];
                            const indices = [];
                            before.forEach(b => {
                                if (b.isMedia) {
                                    imgs.push(...b.images);
                                    vids.push(...b.videos);
                                    indices.push(b.idx);
                                }
                            });
                            if (!skipAfter) {
                                after.forEach(b => {
                                    if (b.isMedia) {
                                        imgs.push(...b.images);
                                        vids.push(...b.videos);
                                        indices.push(b.idx);
                                    }
                                });
                            }
                            return {
                                caseType: "Trường hợp 3",
                                caseDescription: "Media bị chia nhỏ cực đoan",
                                assignedMediaIndices: indices,
                                images: [...new Set(imgs)],
                                videos: [...new Set(vids)]
                            };
                        };

                        const processCase4 = (before, after, skipAfter = false) => {
                            const imgs = [];
                            const vids = [];
                            const indices = [];
                            before.forEach(b => {
                                if (b.isMedia) {
                                    imgs.push(...b.images);
                                    vids.push(...b.videos);
                                    indices.push(b.idx);
                                }
                            });
                            if (!skipAfter) {
                                after.forEach(b => {
                                    if (b.isMedia) {
                                        imgs.push(...b.images);
                                        vids.push(...b.videos);
                                        indices.push(b.idx);
                                    }
                                });
                            }
                            return {
                                caseType: "Trường hợp 4",
                                caseDescription: "Kẹp bánh mì (Media nằm cả trước và sau chữ)",
                                assignedMediaIndices: indices,
                                images: [...new Set(imgs)],
                                videos: [...new Set(vids)]
                            };
                        };

                        const processCase5 = (before, after, skipAfter = false) => {
                            const imgs = [];
                            const vids = [];
                            const indices = [];
                            before.forEach(b => {
                                if (b.isMedia && b.images.length > 0) {
                                    imgs.push(...b.images);
                                    indices.push(b.idx);
                                }
                            });
                            if (!skipAfter) {
                                after.forEach(b => {
                                    if (b.isMedia && b.videos.length > 0) {
                                        vids.push(...b.videos);
                                        indices.push(b.idx);
                                    }
                                });
                            }
                            return {
                                caseType: "Trường hợp 5",
                                caseDescription: "Ảnh trước, Video sau chữ",
                                assignedMediaIndices: indices,
                                images: [...new Set(imgs)],
                                videos: [...new Set(vids)]
                            };
                        };

                        const processStandard = (before, after, skipAfter = false) => {
                            const imgs = [];
                            const vids = [];
                            const indices = [];
                            before.forEach(b => {
                                if (b.isMedia) {
                                    imgs.push(...b.images);
                                    vids.push(...b.videos);
                                    indices.push(b.idx);
                                }
                            });
                            if (!skipAfter) {
                                after.forEach(b => {
                                    if (b.isMedia) {
                                        imgs.push(...b.images);
                                        vids.push(...b.videos);
                                        indices.push(b.idx);
                                    }
                                });
                            }
                            return {
                                caseType: "Chuẩn",
                                caseDescription: "Gửi chuẩn (1 album hoặc 1 cụm media duy nhất)",
                                assignedMediaIndices: indices,
                                images: [...new Set(imgs)],
                                videos: [...new Set(vids)]
                            };
                        };

                        const processKhac = (before, after, skipAfter = false) => {
                            const imgs = [];
                            const vids = [];
                            const indices = [];
                            before.forEach(b => {
                                if (b.isMedia) {
                                    imgs.push(...b.images);
                                    vids.push(...b.videos);
                                    indices.push(b.idx);
                                }
                            });
                            if (!skipAfter) {
                                after.forEach(b => {
                                    if (b.isMedia) {
                                        imgs.push(...b.images);
                                        vids.push(...b.videos);
                                        indices.push(b.idx);
                                    }
                                });
                            }
                            return {
                                caseType: "Khác",
                                caseDescription: "Lộn xộn tự do",
                                assignedMediaIndices: indices,
                                images: [...new Set(imgs)],
                                videos: [...new Set(vids)]
                            };
                        };
                        
                        // Case 5: Album/images before anchor, video bubble after anchor
                        const isCase5 = () => {
                            const hasImagesBeforeOnly = mediaBefore.some(b => b.images.length > 0 && b.videos.length === 0);
                            const hasVideosAfterOnly = mediaAfter.some(b => b.videos.length > 0 && b.images.length === 0);
                            const noVideoBefore = !mediaBefore.some(b => b.videos.length > 0);
                            const noImageAfter = !mediaAfter.some(b => b.images.length > 0);
                            return hasImagesBeforeOnly && hasVideosAfterOnly && noVideoBefore && noImageAfter;
                        };
                        
                        // Case 4: Kẹp bánh mì
                        const isCase4 = () => {
                            return mediaBefore.length > 0 && mediaAfter.length > 0;
                        };
                        
                        // Case 1: Tách rời Video & Album ảnh
                        const isCase1 = () => {
                            if (mediaBefore.length >= 2 && mediaAfter.length === 0) {
                                const hasAlbum = mediaBefore.some(b => b.images.length >= 2);
                                const hasSeparateVideo = mediaBefore.some(b => b.videos.length > 0 && b.images.length === 0);
                                return hasAlbum && hasSeparateVideo;
                            }
                            if (mediaAfter.length >= 2 && mediaBefore.length === 0) {
                                const hasAlbum = mediaAfter.some(b => b.images.length >= 2);
                                const hasSeparateVideo = mediaAfter.some(b => b.videos.length > 0 && b.images.length === 0);
                                return hasAlbum && hasSeparateVideo;
                            }
                            return false;
                        };
                        
                        // Case 2: Có tin nhắn đã thu hồi trong Album + Ảnh lẻ
                        const isCase2 = () => {
                            const hasRecalledBefore = bubblesBefore.some(b => b.isRecalled);
                            const hasRecalledAfter = bubblesAfter.some(b => b.isRecalled);
                            return (hasRecalledBefore || hasRecalledAfter) && (uniqueImages.length > 0 || uniqueVideos.length > 0);
                        };
                        
                        // Case 3: Media bị chia nhỏ cực đoan
                        const isCase3 = () => {
                            const totalMediaBubbles = mediaBefore.length + mediaAfter.length;
                            return totalMediaBubbles >= 3;
                        };
                        
                        // Standard Case
                        const isStandard = () => {
                            const totalMediaBubbles = mediaBefore.length + mediaAfter.length;
                            return totalMediaBubbles === 1;
                        };
                        
                        if (isCase2()) {
                            return processCase2(bubblesBefore, bubblesAfter, skipAfter);
                        } else if (isCase3()) {
                            return processCase3(bubblesBefore, bubblesAfter, skipAfter);
                        } else if (isCase5()) {
                            return processCase5(bubblesBefore, bubblesAfter, skipAfter);
                        } else if (isCase4()) {
                            return processCase4(bubblesBefore, bubblesAfter, skipAfter);
                        } else if (isCase1()) {
                            return processCase1(bubblesBefore, bubblesAfter, skipAfter);
                        } else if (isStandard()) {
                            return processStandard(bubblesBefore, bubblesAfter, skipAfter);
                        } else if (uniqueImages.length > 0 || uniqueVideos.length > 0) {
                            return processKhac(bubblesBefore, bubblesAfter, skipAfter);
                        } else {
                            return {
                                caseType: "Không xác định",
                                caseDescription: "Không khớp các mẫu nhận dạng",
                                assignedMediaIndices: [],
                                images: [],
                                videos: []
                            };
                        }
                    };

                    textBubbles.forEach(tb => {
                        const res = classifyCase(tb.idx);
                        tb.caseType = res.caseType;
                        tb.caseDescription = res.caseDescription;
                        tb.assignedMediaIndices = res.assignedMediaIndices;
                        tb.images = res.images;
                        tb.videos = res.videos;
                    });
                    const targetTb = textBubbles.find(tb => tb.trackingNumbers.includes(trackingNumber));
                    if (!targetTb) return null;
                    
                    document.querySelectorAll('.zalo-text-target-bubble').forEach(el => el.classList.remove('zalo-text-target-bubble'));
                    allMsgItems[targetTb.idx].classList.add('zalo-text-target-bubble');
                    
                    document.querySelectorAll('.zalo-video-temp-target').forEach(el => el.classList.remove('zalo-video-temp-target'));
                    document.querySelectorAll('[class*="zalo-target-bubble-"]').forEach(el => {
                        Array.from(el.classList).forEach(c => {
                            if (c.startsWith('zalo-target-bubble-')) el.classList.remove(c);
                        });
                    });
                    
                    let firstBubble = null;
                    let count = 1;
                    if (targetTb.assignedMediaIndices && targetTb.assignedMediaIndices.length > 0) {
                        targetTb.assignedMediaIndices.forEach((idx, order) => {
                            allMsgItems[idx].classList.add(`zalo-target-bubble-${order}`);
                        });
                        firstBubble = allMsgItems[targetTb.assignedMediaIndices[0]];
                        count = targetTb.assignedMediaIndices.length;
                    } else {
                        firstBubble = allMsgItems[targetTb.idx];
                        count = 1;
                    }
                    
                    if (!skipScrollSearch && firstBubble) {
                        firstBubble.scrollIntoView({ block: 'center' });
                    }
                    
                    return { success: true, count: count, targetTb: targetTb };
                } catch (e) {
                    return { success: false, error: e.toString() };
                }
            }
        """, {"trackingNumber": tracking_number, "skipScrollSearch": skip_scroll_search, "reverseScan": reverse_scan})
        
        if marker_result and marker_result.get("success"):
            target_tb = marker_result.get("targetTb")
            if target_tb:
                target_tb["trackingNumber"] = tracking_number
                if target_tb.get("caseType") and target_tb.get("caseType") not in ["Chuẩn", "Không xác định"]:
                    self.learn_messy_package(target_tb)
                    
        total_bubbles = marker_result.get("count", 1) if marker_result and marker_result.get("success") else 0
        print(f"Đã phát hiện {total_bubbles} bong bóng chứa dữ liệu media.")
        
        if total_bubbles == 0:
            print(f"[Zalo Download] Marker không tìm thấy tin nhắn. Sẽ thử tải trực tiếp từ URLs đã thu thập: {len(package.get('images', []))} ảnh, {len(package.get('videos', []))} video.")
        

                
        all_downloaded_images = []
        all_downloaded_videos = []
        
        for bubble_idx in range(total_bubbles):
            print(f"Đang tải dữ liệu từ bong bóng thứ {bubble_idx+1}/{total_bubbles}...")
            if progress_callback:
                await progress_callback(f"Đang tải dữ liệu từ bong bóng {bubble_idx+1}/{total_bubbles}...")
                
            # Locate, tag, and center the active bubble fresh in this iteration!
            tag_success = await self.zalo_page.evaluate(r"""
                async ({ trackingNumber, bubbleIdx, reverseScan }) => {
                    try {
                        const allMsgItems = Array.from(document.querySelectorAll(window.zalo_chat_item || '.chat-item'));
                        
                        const hasReaction = (item) => {
                            const v2space = item.querySelector(window.zalo_reaction_space || '.message-reaction-v2-space');
                            if (v2space) {
                                const rect = v2space.getBoundingClientRect();
                                if (rect.height > 0) return true;
                            }
                            return false;
                        };


                        const getImagesInItem = (item) => {
                            const imgs = Array.from(item.querySelectorAll('img'));
                            const urls = [];
                            imgs.forEach(img => {
                                const rect = img.getBoundingClientRect();
                                const src = (img.getAttribute('src') || img.src || '').toLowerCase();
                                const className = (img.className || '').toLowerCase();
                                if (
                                    className.includes('avatar') || src.includes('avatar') || 
                                    className.includes('logo') || src.includes('logo') || 
                                    className.includes('emoji') || src.includes('emoji') ||
                                    className.includes('sticker') || src.includes('sticker')
                                ) return;
                                if (rect.width > 30 || rect.height > 30 || img.naturalWidth > 30) {
                                    const url = img.getAttribute('data-src') || img.src || '';
                                    if (url) urls.push(url);
                                }
                            });
                            return urls;
                        };

                        const getVideosInItem = (item) => {
                            const videos = [];
                            const seenVideoCoords = new Set();
                            const allElements = Array.from(item.querySelectorAll('*'));
                            
                            allElements.forEach(el => {
                                const rect = el.getBoundingClientRect();
                                if (rect.width > 20 && rect.height > 20) {
                                    const classStr = String(el.className && typeof el.className === 'object' ? el.className.baseVal || '' : el.className || '').toLowerCase();
                                    const text = (el.textContent || '').trim();
                                    const tagName = el.tagName.toLowerCase();
                                    
                                    const isVideoTag = tagName === 'video';
                                    const isDurationPattern = /^\d{1,2}:\d{2}(:\d{2})?$/.test(text);
                                    const isMsgTime = classStr.includes('time') || classStr.includes('send-time');
                                    const isDuration = isDurationPattern && !isMsgTime;
                                    const hasVideoClass = (classStr.includes('play') && !classStr.includes('display')) || classStr.includes('video') || classStr.includes('duration');
                                    
                                    if (isVideoTag || isDuration || hasVideoClass) {
                                        let container = el;
                                        let foundContainer = false;
                                        
                                        const elClass = String(el.className && typeof el.className === 'object' ? el.className.baseVal || '' : el.className || '').toLowerCase();
                                        if (elClass.includes('card--group-photo__row__item') || elClass.includes('album__item') || (elClass.includes('video-message') && !elClass.includes('duration')) || (elClass.includes('video') && !elClass.includes('chat-item') && !elClass.includes('msg-item') && !elClass.includes('duration'))) {
                                            foundContainer = true;
                                        }
                                        
                                        if (!foundContainer) {
                                            let p = el.parentElement;
                                            for (let d = 0; d < 5 && p; d++) {
                                                const pClass = String(p.className && typeof p.className === 'object' ? p.className.baseVal || '' : p.className || '').toLowerCase();
                                                if (pClass.includes('card--group-photo__row__item') || pClass.includes('album__item') || (pClass.includes('video-message') && !pClass.includes('duration')) || (pClass.includes('video') && !pClass.includes('chat-item') && !pClass.includes('msg-item') && !pClass.includes('duration'))) {
                                                    container = p;
                                                    foundContainer = true;
                                                    break;
                                                }
                                                p = p.parentElement;
                                            }
                                        }
                                        
                                        if (!foundContainer) {
                                            let p2 = el.parentElement;
                                            for (let d = 0; d < 4 && p2; d++) {
                                                const p2Class = String(p2.className && typeof p2.className === 'object' ? p2.className.baseVal || '' : p2.className || '').toLowerCase();
                                                if (p2.querySelector('img')) {
                                                    container = p2;
                                                    foundContainer = true;
                                                    break;
                                                }
                                                if (p2Class.includes('chat-item') || p2Class.includes('msg-item')) break;
                                                p2 = p2.parentElement;
                                            }
                                        }
                                        const hasImg = container.querySelector('img') !== null;
                                        const hasBg = container.style.backgroundImage && container.style.backgroundImage !== 'none';
                                        
                                        if (isVideoTag || foundContainer || hasImg || hasBg) {
                                            const cRect = container.getBoundingClientRect();
                                            const cx = Math.round(cRect.left);
                                            const cy = Math.round(cRect.top + window.scrollY);
                                            const coordKey = `${cx}_${cy}`;
                                            
                                            if (!seenVideoCoords.has(coordKey)) {
                                                seenVideoCoords.add(coordKey);
                                                let url = '';
                                                const img = container.querySelector('img');
                                                if (img) {
                                                    url = img.getAttribute('data-src') || img.src || '';
                                                } else {
                                                    const bg = container.style.backgroundImage || window.getComputedStyle(container).backgroundImage;
                                                    if (bg && bg !== 'none') {
                                                        const match = bg.match(/url\(["']?(.*?)["']?\)/);
                                                        if (match) url = match[1];
                                                    }
                                                }
                                                if (!url && isVideoTag) {
                                                    url = container.src || container.getAttribute('src') || '';
                                                }
                                                if (!url) {
                                                    if (isDurationPattern && !hasImg && !hasBg) return;
                                                    url = 'placeholder_video_url';
                                                }
                                                videos.push(url);
                                            }
                                        }
                                    }
                                }
                            });
                            return videos;
                        };

                        const isRecalled = (item) => {
                            const text = item.innerText || '';
                            return text.includes('Đã thu hồi') || text.includes('tin nhắn bị xóa');
                        };

                        // 1. Identify senders
                        allMsgItems.forEach(item => {
                            const className = (item.className && typeof item.className === 'string' ? item.className : '').toLowerCase();
                            const innerHTML = item.innerHTML || '';
                            if (className.includes('me') || className.includes('-send') || innerHTML.includes('card--send') || innerHTML.includes('message-me')) {
                                item.sender = "self";
                            } else {
                                item.sender = "them";
                            }
                        });

                        // 2. Find Anchors
                        const textBubbles = [];
                        allMsgItems.forEach((item, idx) => {
                            const text = item.innerText || '';
                            const matches = text.match(/\b\d{11,12}\b/g) || [];
                            const trackingPatterns = text.match(/(?:Mã vận đơn|tracking|mã đơn)\s*:?\s*(\d{11,12})\b/gi) || [];
                            const allTrackings = [...new Set([...matches, ...trackingPatterns.map(p => p.match(/\d{11,12}/)).filter(m => m).map(m => m[0])])];
                            if (allTrackings.length > 0) {
                                textBubbles.push({
                                    idx: idx,
                                    trackingNumbers: allTrackings,
                                    assignedMediaIndices: [],
                                    sender: item.sender
                                });
                            }
                        });

                        // 3. Bi-directional Search for Media
                        let pinnedIdx = -1; 
                        
                        textBubbles.forEach(anchor => {
                            // Scan UP
                            let imgsUp = [];
                            let vidsUp = [];
                            let upIndices = [];
                            for (let i = anchor.idx - 1; i >= 0; i--) {
                                const neighbor = allMsgItems[i];
                                if (pinnedIdx !== -1 && i < pinnedIdx) break;
                                if (isRecalled(neighbor)) continue; // Filter Garbage
                                
                                if (neighbor.sender !== anchor.sender) break; // Boundary 1: Different Sender
                                
                                const text = neighbor.innerText || '';
                                const neighborTrks = [...(text.match(/\b\d{11,12}\b/g) || []), ...(text.match(/(?:Mã vận đơn|tracking|mã đơn)\s*:?\s*(\d{11,12})\b/gi) || []).map(p=>p.match(/\d{11,12}/)).filter(m=>m).map(m=>m[0])];
                                if (neighborTrks.length > 0) break; // Boundary 2: Another Anchor
                                
                                const imgs = getImagesInItem(neighbor);
                                const vids = getVideosInItem(neighbor);
                                if (imgs.length > 0 || vids.length > 0) {
                                    upIndices.push(i);
                                    imgsUp.push(...imgs.filter(url => !vids.includes(url)));
                                    vidsUp.push(...vids);
                                }
                            }
                            
                            anchor.assignedMediaIndices.push(...upIndices);
                            
                            let skipDown = false;
                            if (reverseScan) {
                                const uniqueImgUp = [...new Set(imgsUp)];
                                const uniqueVidUp = [...new Set(vidsUp)];
                                if (uniqueImgUp.length >= 3 && uniqueVidUp.length >= 1) {
                                    skipDown = true;
                                }
                            }
                            
                            if (!skipDown) {
                                // Scan DOWN
                                for (let i = anchor.idx + 1; i < allMsgItems.length; i++) {
                                    const neighbor = allMsgItems[i];
                                    if (isRecalled(neighbor)) continue; // Filter Garbage
                                    
                                    if (neighbor.sender !== anchor.sender) break; // Boundary 1: Different Sender
                                    
                                    const text = neighbor.innerText || '';
                                    const neighborTrks = [...(text.match(/\b\d{11,12}\b/g) || []), ...(text.match(/(?:Mã vận đơn|tracking|mã đơn)\s*:?\s*(\d{11,12})\b/gi) || []).map(p=>p.match(/\d{11,12}/)).filter(m=>m).map(m=>m[0])];
                                    if (neighborTrks.length > 0) break; // Boundary 2: Another Anchor
                                    
                                    const imgs = getImagesInItem(neighbor);
                                    const vids = getVideosInItem(neighbor);
                                    if (imgs.length > 0 || vids.length > 0) {
                                        anchor.assignedMediaIndices.push(i);
                                    }
                                }
                            }
                            
                            // Deduplicate and Sort
                            anchor.assignedMediaIndices = [...new Set(anchor.assignedMediaIndices)].sort((a,b) => a - b);
                        });


                        
                        const targetTb = textBubbles.find(tb => tb.trackingNumbers.includes(trackingNumber));
                        if (!targetTb) return { success: false, error: 'Không tìm thấy tin nhắn chứa mã.' };
                        
                        document.querySelectorAll('.zalo-text-target-bubble').forEach(el => el.classList.remove('zalo-text-target-bubble'));
                        allMsgItems[targetTb.idx].classList.add('zalo-text-target-bubble');
                        
                        document.querySelectorAll('.zalo-video-temp-target').forEach(el => el.classList.remove('zalo-video-temp-target'));
                        document.querySelectorAll('[class*="zalo-target-bubble-"]').forEach(el => {
                            Array.from(el.classList).forEach(c => {
                                if (c.startsWith('zalo-target-bubble-')) el.classList.remove(c);
                            });
                        });
                        
                        let targetBubble = null;
                        if (targetTb.assignedMediaIndices && targetTb.assignedMediaIndices.length > 0) {
                            if (bubbleIdx < targetTb.assignedMediaIndices.length) {
                                targetBubble = allMsgItems[targetTb.assignedMediaIndices[bubbleIdx]];
                                targetBubble.classList.add(`zalo-target-bubble-${bubbleIdx}`);
                            }
                        } else {
                            if (bubbleIdx === 0) {
                                targetBubble = allMsgItems[targetTb.idx];
                            }
                        }
                        
                        if (targetBubble) {
                            targetBubble.classList.add('zalo-video-temp-target');
                            targetBubble.scrollIntoView({ block: 'center' });
                            return { success: true };
                        }
                        
                        return { success: false, error: 'Không tìm thấy media bubble tương ứng với bubbleIdx.' };
                    } catch (e) {
                        return { success: false, error: e.toString() };
                    }
                }
            """, {"trackingNumber": tracking_number, "bubbleIdx": bubble_idx, "reverseScan": reverse_scan})
            
            if not tag_success or not tag_success.get("success"):
                print(f"[Zalo Download] Không thể gắn tag bong bóng thứ {bubble_idx+1}: {tag_success.get('error') if tag_success else 'unknown'}")
                continue
            
            downloaded_images = []
            downloaded_videos = []
            bulk_download_success = False
            
            # --- LAYER 1: Attempt Grouped Media Bulk ZIP Download ---
            try:
                # Hover over the media bubble to trigger action buttons (like bulk download / More button)
                media_bubble_locator = self.zalo_page.locator('.zalo-video-temp-target .message-content-render, .zalo-video-temp-target .message-frame, .zalo-video-temp-target .message-non-frame').first
                await media_bubble_locator.hover(timeout=3000)
                await asyncio.sleep(0.2)
                
                # Check for "More" button inside the media bubble
                more_eval = await self.zalo_page.evaluate("""
                    () => {
                        const videoEl = document.querySelector('.zalo-video-temp-target');
                        if (!videoEl) return { success: false, error: 'Không tìm thấy media bubble.' };
                        
                        const findMoreBtn = () => {
                            const allElements = Array.from(videoEl.querySelectorAll('*'));
                            for (const el of allElements) {
                                const className = (el.className || '').toString().toLowerCase();
                                const title = (el.getAttribute('title') || '').toLowerCase();
                                const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
                                
                                if (
                                    className.includes('more') || 
                                    className.includes('dot') || 
                                    className.includes('ellipsis') ||
                                    title.includes('thêm') || 
                                    title.includes('khác') ||
                                    ariaLabel.includes('thêm') || 
                                    ariaLabel.includes('khác')
                                ) {
                                    const rect = el.getBoundingClientRect();
                                    if (rect.width > 0 && rect.height > 0) {
                                        return el;
                                    }
                                }
                            }
                            return null;
                        };
                        
                        const moreBtn = findMoreBtn();
                        if (moreBtn) {
                            moreBtn.setAttribute('data-temp-more-click', 'true');
                            return { success: true };
                        }
                        return { success: false, error: 'Không tìm thấy nút Thêm (...) trong bong bóng tin nhắn.' };
                    }
                """)
                
                if more_eval and more_eval.get("success"):
                    print("Nhấp vào nút Thêm (...)")
                    await self.zalo_page.click('.zalo-video-temp-target [data-temp-more-click="true"]', timeout=3000)
                    await asyncio.sleep(0.2)
                    
                    # Search context menu for "Lưu X ảnh/video về máy" or similar
                    menu_eval = await self.zalo_page.evaluate("""
                        () => {
                            const items = Array.from(document.querySelectorAll('div, li, span, a'));
                            const downloadItem = items.find(el => {
                                const text = (el.textContent || '').trim().toLowerCase();
                                const matches = (text.includes('về máy') && (text.includes('ảnh') || text.includes('video') || text.includes('file'))) ||
                                                text === 'lưu về máy' || text === 'tải về' || text === 'tải xuống' ||
                                                text.includes('lưu về máy') || text.includes('tải về') || text.includes('download') || text.includes('save');
                                if (!matches) return false;
                                
                                const rect = el.getBoundingClientRect();
                                if (rect.width === 0 || rect.height === 0 || rect.left <= 220) return false;
                                
                                const childMatches = Array.from(el.querySelectorAll('*')).some(child => {
                                    const childText = (child.textContent || '').trim().toLowerCase();
                                    return (childText.includes('về máy') && (childText.includes('ảnh') || childText.includes('video') || childText.includes('file'))) ||
                                           childText === 'lưu về máy' || childText === 'tải về' || childText === 'tải xuống' ||
                                           childText.includes('lưu về máy') || childText.includes('tải về') || childText.includes('download') || childText.includes('save');
                                });
                                return !childMatches;
                            });
                            
                            if (downloadItem) {
                                downloadItem.setAttribute('data-temp-menu-download-click', 'true');
                                return { success: true, text: downloadItem.textContent.trim() };
                            }
                            return { success: false, error: 'Không tìm thấy tùy chọn Tải/Lưu trong menu.' };
                        }
                    """)
                    
                    if menu_eval and menu_eval.get("success"):
                        print(f"Đang click tùy chọn tải về: '{menu_eval['text']}'...")
                        
                        async with self.zalo_page.expect_download(timeout=15000) as download_info:
                            await self.zalo_page.click('[data-temp-menu-download-click="true"]', timeout=3000)
                        download = await download_info.value
                        
                        temp_zip_path = os.path.join(package_dir, "temp_" + download.suggested_filename)
                        await download.save_as(temp_zip_path)
                        
                        # Process downloaded ZIP file
                        if temp_zip_path.lower().endswith(".zip") and os.path.exists(temp_zip_path) and os.path.getsize(temp_zip_path) > 10000:
                            import zipfile
                            import shutil
                            
                            print("Đã tải thành công file ZIP, đang giải nén...")
                            temp_extract_dir = os.path.join(package_dir, f"temp_extract_{bubble_idx}")
                            os.makedirs(temp_extract_dir, exist_ok=True)
                            
                            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                                zip_ref.extractall(temp_extract_dir)
                                
                            # Separate extracted images and videos
                            extracted_files = [os.path.join(temp_extract_dir, f) for f in os.listdir(temp_extract_dir)]
                            
                            ext_images = []
                            ext_videos = []
                            for f in extracted_files:
                                ext = os.path.splitext(f)[1].lower()
                                if ext in [".jpg", ".jpeg", ".png", ".gif"]:
                                    ext_images.append(f)
                                elif ext in [".mp4", ".mov", ".avi", ".3gp"]:
                                    ext_videos.append(f)
                                    
                            ext_images.sort()
                            ext_videos.sort()
                            
                            # Move and rename
                            for idx, img_path in enumerate(ext_images):
                                target_img = os.path.join(package_dir, f"image_temp_{bubble_idx}_{idx+1}.jpg")
                                if os.path.exists(target_img):
                                    os.remove(target_img)
                                os.rename(img_path, target_img)
                                downloaded_images.append(target_img)
                                
                            for idx, vid_path in enumerate(ext_videos):
                                target_vid = os.path.join(package_dir, f"video_temp_{bubble_idx}_{idx+1}.mp4")
                                if os.path.exists(target_vid):
                                    os.remove(target_vid)
                                os.rename(vid_path, target_vid)
                                downloaded_videos.append(target_vid)
                                
                            # Clean up
                            shutil.rmtree(temp_extract_dir, ignore_errors=True)
                            os.remove(temp_zip_path)
                            bulk_download_success = True
                            
                        else:
                            # If it was not a zip, it is a single file download
                            print("Đang xử lý file tải đơn...")
                            ext = os.path.splitext(temp_zip_path)[1].lower()
                            if ext in [".mp4", ".mov", ".avi", ".3gp"]:
                                target_path = os.path.join(package_dir, f"video_temp_{bubble_idx}_1.mp4")
                                if os.path.exists(target_path):
                                    os.remove(target_path)
                                os.rename(temp_zip_path, target_path)
                                if os.path.exists(target_path) and os.path.getsize(target_path) > 10000:
                                    downloaded_videos.append(target_path)
                                    bulk_download_success = True
                            else:
                                target_path = os.path.join(package_dir, f"image_temp_{bubble_idx}_1.jpg")
                                if os.path.exists(target_path):
                                    os.remove(target_path)
                                os.rename(temp_zip_path, target_path)
                                if os.path.exists(target_path) and os.path.getsize(target_path) > 5000:
                                    downloaded_images.append(target_path)
                                    bulk_download_success = True
                                    
                            if not bulk_download_success and os.path.exists(temp_zip_path):
                                os.remove(temp_zip_path)
            except Exception as e_bulk:
                print(f"Phương pháp Bulk ZIP gặp lỗi tại bong bóng {bubble_idx+1}: {e_bulk}. Sẽ chuyển sang phương pháp Lightbox dự phòng...")
                # Escape menu if open
                await self.zalo_page.keyboard.press("Escape")
                await asyncio.sleep(0.5)

            # --- LAYER 2: Fallback to Lightbox loop download ---
            if not bulk_download_success:
                print(f"Đang chạy phương pháp Lightbox tải lẻ dự phòng cho bong bóng {bubble_idx+1}...")
                try:
                    # Count media items in this bubble
                    media_count = await self.zalo_page.evaluate("""
                        () => {
                            const bubble = document.querySelector('.zalo-video-temp-target');
                            if (!bubble) return 1;
                            
                            const imgs = Array.from(bubble.querySelectorAll('img')).filter(img => {
                                const src = img.getAttribute('src') || '';
                                const className = img.className || '';
                                if (className.includes('avatar') || src.includes('avatar') || src.includes('logo') || src.includes('emoji')) return false;
                                return true;
                            });
                            
                            const videos = Array.from(bubble.querySelectorAll('video'));
                            
                            const positions = new Set();
                            imgs.concat(videos).forEach(el => {
                                const rect = el.getBoundingClientRect();
                                if (rect.width > 20 && rect.height > 20) {
                                    const x = Math.round(rect.left / 10) * 10;
                                    const y = Math.round(rect.top / 10) * 10;
                                    positions.add(`${x}_${y}`);
                                }
                            });
                            return positions.size || 1;
                        }
                    """)
                    print(f"Số lượng file media phát hiện trong bong bóng này: {media_count}")
                    
                    if media_count > 0:
                        # Click the first thumbnail inside the bubble to open Lightbox
                        await self.zalo_page.locator('.zalo-video-temp-target img, .zalo-video-temp-target video, .zalo-video-temp-target [class*="play"]').first.click(timeout=3000)
                        await asyncio.sleep(0.4)
                        
                        downloaded_images = []
                        downloaded_videos = []
                        seen_srcs = set()
                        img_idx = 1
                        vid_idx = 1
                        
                        for step in range(media_count):
                            if progress_callback:
                                await progress_callback(f"Bong bóng {bubble_idx+1}: Đang tải file {step+1}/{media_count} qua Lightbox...")
                                
                            # Try to detect active media (with retries if loading)
                            active_media = None
                            for retry in range(4):
                                active_media = await self.zalo_page.evaluate("""
                                    () => {
                                        // 1. Detect video element in Lightbox
                                        const videos = Array.from(document.querySelectorAll('video')).filter(v => {
                                            const r = v.getBoundingClientRect();
                                            return r.width > 100 && r.height > 100 && window.getComputedStyle(v).opacity !== '0';
                                        });
                                        if (videos.length > 0) {
                                            return { type: 'video', src: videos[0].src };
                                        }
                                        
                                        // 2. Detect image element in Lightbox
                                        const images = Array.from(document.querySelectorAll('img')).filter(img => {
                                            const r = img.getBoundingClientRect();
                                            const isLarge = r.width > 200 && r.height > 200;
                                            const isCentered = r.left >= 0 && r.right <= window.innerWidth && r.top >= 0 && r.bottom <= window.innerHeight;
                                            const src = img.src || '';
                                            const isNotAvatar = !src.includes('avatar') && !src.includes('logo') && !img.className.includes('avatar');
                                            return isLarge && isNotAvatar;
                                        });
                                        if (images.length > 0) {
                                            images.sort((a, b) => {
                                                const rA = a.getBoundingClientRect();
                                                const rB = b.getBoundingClientRect();
                                                const centerDistA = Math.abs((rA.left + rA.width/2) - window.innerWidth/2);
                                                const centerDistB = Math.abs((rB.left + rB.width/2) - window.innerWidth/2);
                                                return centerDistA - centerDistB;
                                            });
                                            return { type: 'image', src: images[0].src };
                                        }
                                        return null;
                                    }
                                """)
                                if active_media and active_media.get("src"):
                                    break
                                await asyncio.sleep(0.3)
                                
                            if not active_media or not active_media.get("src"):
                                print(f"Không nhận dạng được file media hoạt động ở bước {step+1}.")
                                if step < media_count - 1:
                                    await self.zalo_page.keyboard.press("ArrowRight")
                                    await asyncio.sleep(0.25)
                                continue
                                
                            media_src = active_media["src"]
                            media_type = active_media["type"]
                            
                            if media_src in seen_srcs:
                                print(f"File media {media_src} đã được tải trước đó, bỏ qua...")
                                if step < media_count - 1:
                                    await self.zalo_page.keyboard.press("ArrowRight")
                                    await asyncio.sleep(0.25)
                                continue
                                
                            seen_srcs.add(media_src)
                            
                            # Fetch the blob contents via JS
                            fetch_result = await self.zalo_page.evaluate("""
                                async (src) => {
                                    try {
                                        const res = await fetch(src);
                                        const blob = await res.blob();
                                        return new Promise((resolve) => {
                                            const reader = new FileReader();
                                            reader.onloadend = () => resolve({ success: true, base64: reader.result.split(',')[1] });
                                            reader.onerror = () => resolve({ success: false, error: 'Lỗi đọc file blob' });
                                            reader.readAsDataURL(blob);
                                        });
                                    } catch(e) {
                                        return { success: false, error: e.message };
                                    }
                                }
                            """, media_src)
                            
                            if fetch_result and fetch_result.get("success"):
                                base64_data = fetch_result["base64"]
                                if media_type == "video":
                                    target_path = os.path.join(package_dir, f"video_temp_{bubble_idx}_{vid_idx}.mp4")
                                    vid_idx += 1
                                    with open(target_path, "wb") as f:
                                        f.write(base64.b64decode(base64_data))
                                    if os.path.exists(target_path) and os.path.getsize(target_path) > 10000:
                                        downloaded_videos.append(target_path)
                                        print(f"Đã lưu video lẻ qua Lightbox: {target_path}")
                                else:
                                    target_path = os.path.join(package_dir, f"image_temp_{bubble_idx}_{img_idx}.jpg")
                                    img_idx += 1
                                    with open(target_path, "wb") as f:
                                        f.write(base64.b64decode(base64_data))
                                    if os.path.exists(target_path) and os.path.getsize(target_path) > 5000:
                                        downloaded_images.append(target_path)
                                        print(f"Đã lưu ảnh lẻ qua Lightbox: {target_path}")
                            else:
                                print(f"Lỗi fetch base64 ở bước {step+1}: {fetch_result.get('error') if fetch_result else 'unknown'}")
                                
                            # Navigate to next item
                            if step < media_count - 1:
                                await self.zalo_page.keyboard.press("ArrowRight")
                                await asyncio.sleep(0.35)
                                
                        # Close Lightbox
                        await self.zalo_page.keyboard.press("Escape")
                        await asyncio.sleep(0.25)
                except Exception as e_lb:
                    print(f"Lỗi tải qua Lightbox ở bong bóng {bubble_idx+1}: {e_lb}")
                    await self.zalo_page.keyboard.press("Escape")
                    await asyncio.sleep(0.25)
                    
            # Accumulate results
            all_downloaded_images.extend(downloaded_images)
            all_downloaded_videos.extend(downloaded_videos)
        # --- PHASE 1.5: Barcode Verification on Downloaded Images ---
        print(f"[Barcode Verification] Bắt đầu xác thực mã vận đơn bằng Barcode cho đơn {tracking_number}...")
        if progress_callback:
            await progress_callback(f"Đang chạy kiểm tra Barcode trên ảnh...")
            
        ocr_temp_images = []
        for f in os.listdir(package_dir):
            if f.startswith("image_temp_") and f.lower().endswith((".jpg", ".jpeg", ".png")):
                ocr_temp_images.append(os.path.join(package_dir, f))
                
        barcode_matched = False
        found_barcodes_list = []
        for img_path in ocr_temp_images:
            found_barcodes = self.read_barcode_from_image(img_path)
            found_barcodes_list.extend(found_barcodes)
            if tracking_number in found_barcodes:
                barcode_matched = True
                break
                
        if not barcode_matched:
            all_scanned_trackings = self.get_all_scanned_tracking_numbers()
            other_valid = [b for b in found_barcodes_list if b in all_scanned_trackings]
            if other_valid:
                target_tracking = other_valid[0]
                print(f"[Auto-Correction] Phát hiện mã {target_tracking} thay vì {tracking_number}. Tiến hành tự động di chuyển...")
                if progress_callback:
                    await progress_callback(f"[Tự Động Sửa Sai] Chuyển 3 ảnh + 1 video sang đúng đơn {target_tracking}...")
                
                target_folder_name = self.find_folder_for_tracking(target_tracking)
                target_folder_path = os.path.join(DATA_DIR, str(target_folder_name))
                os.makedirs(target_folder_path, exist_ok=True)
                
                for f in os.listdir(package_dir):
                    if f.startswith("image_temp_") or f.startswith("video_temp_"):
                        # Use a timestamp to prevent overwriting existing temp files in target folder
                        ext = os.path.splitext(f)[1]
                        new_name = f.replace(ext, f"_{int(time.time())}{ext}")
                        shutil.move(os.path.join(package_dir, f), os.path.join(target_folder_path, new_name))
                        
                # We return empty arrays because this specific package tracking_number is considered failed (it belonged to another)
                return [], []
            else:
                print(f"[Barcode Verification] Không tìm thấy Barcode nào rõ ràng. Tự động tin tưởng phân cụm ban đầu cho {tracking_number}.")
                if progress_callback:
                    await progress_callback(f"[Barcode] Không thấy mã vạch, hệ thống tự động chốt đơn {tracking_number} theo dự đoán...")

        # --- PHASE 2: Clean up, rename all temp files to standardized final format ---
        for f in os.listdir(package_dir):
            if (f.startswith("image_") or f.startswith("video_")) and not (f.startswith("image_temp_") or f.startswith("video_temp_")):
                try:
                    os.remove(os.path.join(package_dir, f))
                except Exception:
                    pass
                    
        all_temp_images = []
        all_temp_videos = []
        
        for f in os.listdir(package_dir):
            full_p = os.path.join(package_dir, f)
            if os.path.isfile(full_p):
                if f.startswith("image_temp_"):
                    all_temp_images.append(full_p)
                elif f.startswith("video_temp_"):
                    all_temp_videos.append(full_p)
                    
        all_temp_images.sort()
        all_temp_videos.sort()
        
        for idx, temp_p in enumerate(all_temp_images[:3]):
            target_p = os.path.join(package_dir, f"image_{idx+1}.jpg")
            if os.path.exists(target_p):
                try: os.remove(target_p)
                except Exception: pass
            try:
                os.rename(temp_p, target_p)
                final_images.append(target_p)
            except Exception as e:
                print(f"Lỗi đổi tên ảnh: {e}")
                
        for idx, temp_p in enumerate(all_temp_videos[:1]):
            target_p = os.path.join(package_dir, f"video_{idx+1}.mp4")
            if os.path.exists(target_p):
                try: os.remove(target_p)
                except Exception: pass
            try:
                os.rename(temp_p, target_p)
                final_videos.append(target_p)
            except Exception as e:
                print(f"Lỗi đổi tên video: {e}")
                
        # Clean up any leftover temp files
        for f in os.listdir(package_dir):
            if f.startswith("image_temp_") or f.startswith("video_temp_"):
                try:
                    os.remove(os.path.join(package_dir, f))
                except Exception:
                    pass

        # --- LAYER 3: Fallback to Separate Individual Downloads (Direct Fetch) ---
        need_images = max(0, 3 - len(final_images))
        need_videos = max(0, 1 - len(final_videos))
        if need_images > 0 or need_videos > 0:
            print(f"Đang bổ sung file còn thiếu qua Direct Fetch (thiếu {need_images} ảnh, {need_videos} video)...")
            
            downloaded_count = len(final_images)
            for idx, img_url in enumerate(package.get("images", [])):
                if downloaded_count >= 3:
                    break
                if progress_callback:
                    await progress_callback(f"Đang tải ảnh lẻ {downloaded_count+1}/3 cho đơn {tracking_number}...")
                
                filename = f"image_{downloaded_count+1}.jpg"
                filepath = os.path.join(package_dir, filename)
                
                result = await self.zalo_page.evaluate("""
                    async (url) => {
                        try {
                            const res = await fetch(url);
                            const blob = await res.blob();
                            return new Promise((resolve) => {
                                const reader = new FileReader();
                                reader.onloadend = () => resolve({ success: true, base64: reader.result.split(',')[1], type: blob.type });
                                reader.onerror = () => resolve({ success: false });
                                reader.readAsDataURL(blob);
                            });
                        } catch(e) {
                            return { success: false, error: e.message };
                        }
                    }
                """, img_url)
                
                if result and result.get("success"):
                    with open(filepath, "wb") as f:
                        f.write(base64.b64decode(result["base64"]))
                    if os.path.exists(filepath) and os.path.getsize(filepath) > 5000:
                        final_images.append(filepath)
                        downloaded_count += 1
                        print(f"Đã tải ảnh thành công: {filepath}")
                else:
                    print(f"Lỗi tải ảnh {idx+1}: {result.get('error') if result else 'unknown'}")

            downloaded_vid_count = len(final_videos)
            for idx, vid_url in enumerate(package.get("videos", [])):
                if downloaded_vid_count >= 1:
                    break
                if progress_callback:
                    await progress_callback(f"Đang tải video lẻ {downloaded_vid_count+1}/1 cho đơn {tracking_number}...")
                
                filename = f"video_{downloaded_vid_count+1}.mp4"
                filepath = os.path.join(package_dir, filename)
                
                result_fetch = await self.zalo_page.evaluate("""
                    async (url) => {
                        try {
                            const res = await fetch(url);
                            const blob = await res.blob();
                            return new Promise((resolve) => {
                                const reader = new FileReader();
                                reader.onloadend = () => resolve({ success: true, base64: reader.result.split(',')[1], type: blob.type });
                                reader.onerror = () => resolve({ success: false });
                                reader.readAsDataURL(blob);
                            });
                        } catch(e) {
                            return { success: false, error: e.message };
                        }
                    }
                """, vid_url)
                
                if result_fetch and result_fetch.get("success") and "image" not in result_fetch.get("type", ""):
                    with open(filepath, "wb") as f:
                        f.write(base64.b64decode(result_fetch["base64"]))
                    if os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
                        final_videos.append(filepath)
                        downloaded_vid_count += 1
                        print(f"Đã tải video thành công: {filepath}")
                else:
                    print(f"Lỗi tải video {idx+1}: {result_fetch.get('error') if result_fetch else 'unknown'}")
        
        # Relaxed check: Keep whatever files we downloaded, do not delete them.
        # We only print verification success if we have at least 1 image and 1 video (standard JMS requirement).
        if len(final_images) >= 1 and len(final_videos) >= 1:
            print(f"[Zalo Download] Xác thực thành công: Tải được {len(final_images)} ảnh và {len(final_videos)} video.")
        else:
            print(f"[Zalo Download] Cảnh báo: Tải thiếu file minh chứng (Có {len(final_images)} ảnh, {len(final_videos)} video). Vẫn giữ lại các file đã tải.")
            
        return final_images, final_videos

    async def upload_to_jms(self, tracking_number, weight, custom_selectors=None, progress_callback=None):
        """Automates uploading photos and weights to JMS via the 'Đăng ký đổi trọng lượng' popup."""
        status = await self.get_status()
        if status["jms"] == "disconnected":
            raise Exception("Chưa mở hoặc chưa kết nối được tab JMS!")
            
        await self.jms_page.bring_to_front()
        
        # Resolve package directory
        package_dir = None
        for item in os.listdir(DATA_DIR):
            item_path = os.path.join(DATA_DIR, item)
            if os.path.isdir(item_path):
                if os.path.exists(os.path.join(item_path, f"{tracking_number}.txt")):
                    package_dir = item_path
                    break
        
        if not package_dir:
            fallback_dir = os.path.join(DATA_DIR, tracking_number)
            if os.path.exists(fallback_dir) and os.path.isdir(fallback_dir):
                package_dir = fallback_dir

        if not package_dir:
            raise Exception(f"Không tìm thấy thư mục dữ liệu cho mã đơn {tracking_number}!")
            
        # Get list of files to upload
        files = [
            os.path.join(package_dir, f) 
            for f in os.listdir(package_dir) 
            if os.path.isfile(os.path.join(package_dir, f)) and not f.lower().endswith('.txt')
        ]
        if len(files) == 0:
            raise Exception(f"Không có ảnh hay video nào trong thư mục của đơn {tracking_number}!")

        # Bước 1: Click nút "Đăng ký đổi trọng lượng" trên menu trên cùng
        if progress_callback:
            await progress_callback("Đang mở form Đăng ký đổi trọng lượng trên JMS...")
            
        try:
            # Dùng JS để click cho chắc chắn, vì giao diện Vue/ElementUI đôi khi bị overlap
            clicked_open = await self.jms_page.evaluate("""
                () => {
                    const buttons = Array.from(document.querySelectorAll('button, div, span'));
                    const btn = buttons.find(el => {
                        const txt = (el.textContent || '').trim();
                        return txt.includes('Đăng ký đổi trọng') && el.getBoundingClientRect().width > 0;
                    });
                    if (btn) {
                        btn.click();
                        return true;
                    }
                    return false;
                }
            """)
            if not clicked_open:
                # Fallback locator
                await self.jms_page.click("button:has-text('Đăng ký đổi trọng'), span:has-text('Đăng ký đổi trọng')")
        except Exception as e:
            print(f"[JMS] Lỗi khi bấm nút Đăng ký đổi trọng lượng: {e}")
            
        await asyncio.sleep(1.5) # Chờ popup hiện lên
        
        # Bước 2: Nhập mã vận đơn
        if progress_callback:
            await progress_callback(f"Đang nhập mã vận đơn {tracking_number}...")
            
        try:
            await self.jms_page.evaluate("""
                (trk) => {
                    const labels = Array.from(document.querySelectorAll('label'));
                    const trkLabel = labels.find(l => (l.textContent || '').includes('Mã vận đơn'));
                    if (trkLabel && trkLabel.nextElementSibling) {
                        const input = trkLabel.nextElementSibling.querySelector('input');
                        if (input) {
                            input.focus();
                            input.value = trk;
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }
                }
            """, tracking_number)
            # Fallback Playwright fill
            await self.jms_page.fill("label:has-text('Mã vận đơn') + div input, input[placeholder*='Mã vận đơn']", tracking_number, timeout=2000)
        except Exception:
            pass
        await asyncio.sleep(0.5)
        
        # Bước 3: Nhập trọng lượng
        if weight:
            if progress_callback:
                await progress_callback(f"Đang cập nhật cân nặng: {weight} kg...")
                
            try:
                await self.jms_page.evaluate("""
                    (wt) => {
                        const labels = Array.from(document.querySelectorAll('label'));
                        const wtLabel = labels.find(l => (l.textContent || '').includes('Trọng lượng sau khi đổi'));
                        if (wtLabel && wtLabel.nextElementSibling) {
                            const input = wtLabel.nextElementSibling.querySelector('input');
                            if (input) {
                                input.focus();
                                input.value = wt;
                                input.dispatchEvent(new Event('input', { bubbles: true }));
                                input.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        }
                    }
                """, str(weight))
                # Fallback Playwright fill
                await self.jms_page.fill("label:has-text('Trọng lượng sau khi đổi') + div input, input[placeholder*='Trọng lượng']", str(weight), timeout=2000)
            except Exception:
                pass
            await asyncio.sleep(0.5)
            
        # Bước 4: Tải lên từng ảnh và video
        if progress_callback:
            await progress_callback(f"Đang tải lên lần lượt {len(files)} file minh chứng...")
            
        for idx, file_path in enumerate(files):
            try:
                # Find the LAST input[type="file"] in the DOM. ElementUI often creates a new one or keeps one at the end of the upload list
                file_input = self.jms_page.locator("input[type='file']").last
                await file_input.set_input_files(file_path)
                
                # Tính thời gian chờ: Ảnh chờ 2s, Video chờ 5s
                wait_time = 5.0 if file_path.lower().endswith('.mp4') else 2.0
                await asyncio.sleep(wait_time)
            except Exception as e:
                print(f"[JMS] Lỗi khi tải file {file_path}: {e}")
                
        # Bước 5: Bấm Xác nhận
        if progress_callback:
            await progress_callback("Đang bấm Xác nhận...")
            
        try:
            await self.jms_page.evaluate("""
                () => {
                    // Tìm trong footer của dialog
                    const dialogs = Array.from(document.querySelectorAll('.el-dialog'));
                    const activeDialog = dialogs.find(d => d.style.display !== 'none');
                    if (activeDialog) {
                        const btns = Array.from(activeDialog.querySelectorAll('button'));
                        const confirmBtn = btns.find(b => (b.textContent || '').includes('Xác nhận'));
                        if (confirmBtn) {
                            confirmBtn.click();
                            return;
                        }
                    }
                    // Fallback search anywhere
                    const allBtns = Array.from(document.querySelectorAll('button'));
                    const anyConfirm = allBtns.find(b => (b.textContent || '').includes('Xác nhận') && b.getBoundingClientRect().width > 0);
                    if (anyConfirm) anyConfirm.click();
                }
            """)
        except Exception:
            # Fallback locator
            await self.jms_page.click("button:has-text('Xác nhận'), button span:has-text('Xác nhận')")
            
        await asyncio.sleep(2.0) # Wait for submission
        
        return True

    def cleanup_browser_locks(self):
        """Clean up leftover Chrome lock files and ghost processes to prevent launch failures (Exit Code 21)."""
        import subprocess
        import stat
        import time

        print("[Browser Cleanup] Starting browser lock and process cleanup...")
        
        # 1. Kill ghost chrome.exe processes belonging to jms_helper
        try:
            # Filter for chrome.exe with command line containing jms_helper
            cmd = 'powershell -Command "Get-CimInstance Win32_Process -Filter \\"Name = \'chrome.exe\' AND CommandLine LIKE \'%jms_helper%\'\\" | Remove-CimInstance"'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if res.returncode == 0:
                print("[Browser Cleanup] Ghost Chrome processes terminated successfully.")
            else:
                print(f"[Browser Cleanup] PowerShell warning: {res.stderr.strip()}")
        except Exception as e:
            print(f"[Browser Cleanup] Error running ghost process cleanup: {e}")

        # Wait a small moment to let handles release
        time.sleep(0.5)

        # 2. Clean lock files in USER_DATA_DIR
        lock_files = [
            os.path.join(USER_DATA_DIR, "SingletonLock"),
            os.path.join(USER_DATA_DIR, "SingletonCookie"),
            os.path.join(USER_DATA_DIR, "Singleton Socket"),
            os.path.join(USER_DATA_DIR, "lock"),
            os.path.join(USER_DATA_DIR, "Default", "SingletonLock"),
            os.path.join(USER_DATA_DIR, "Default", "SingletonCookie"),
            os.path.join(USER_DATA_DIR, "Default", "Singleton Socket"),
            os.path.join(USER_DATA_DIR, "Default", "lock"),
            os.path.join(USER_DATA_DIR, "Default", "LOCK"),
        ]

        for file_path in lock_files:
            if os.path.exists(file_path):
                try:
                    os.chmod(file_path, stat.S_IWRITE)
                    os.remove(file_path)
                    print(f"[Browser Cleanup] Removed lock file: {file_path}")
                except Exception as ex:
                    print(f"[Browser Cleanup] Could not remove lock file {file_path}: {ex}")

        # Deep clean search for lock files starting with 'Singleton' or named 'lock' (case-insensitive)
        try:
            if os.path.exists(USER_DATA_DIR):
                for root, dirs, files in os.walk(USER_DATA_DIR):
                    for name in files:
                        lower_name = name.lower()
                        if lower_name.startswith("singleton") or lower_name == "lock":
                            fp = os.path.join(root, name)
                            try:
                                os.chmod(fp, stat.S_IWRITE)
                                os.remove(fp)
                                print(f"[Browser Cleanup] Deep clean removed: {fp}")
                            except Exception:
                                pass
        except Exception as e:
            print(f"[Browser Cleanup] Deep clean directory walk error: {e}")

    async def close_browser(self):
        """Closes the Playwright browser context."""
        if self.browser_context:
            await self.browser_context.close()
            self.browser_context = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        return True
