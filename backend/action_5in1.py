import os
from filelock import FileLock
import json
import asyncio
from automation import DATA_DIR

async def run_5in1(automation, progress_callback=None, direction="up", start_tracking=None):
    """Scans Zalo messages, downloading and liking each package one-by-one, stopping at the first already-liked package."""
    status = await automation.get_status()
    if status["zalo"] == "disconnected":
        raise Exception("Chưa mở hoặc chưa kết nối được tab Zalo Web!")

    await automation.zalo_page.bring_to_front()

    # Tự động tìm kiếm và mở nhóm chat "HÀNG QUÁ TRỌNG LƯỢNG"
    if progress_callback:
        await progress_callback("Đang tìm kiếm nhóm 'HÀNG QUÁ TRỌNG LƯỢNG'...")
        
    try:
        search_input = automation.zalo_page.locator('#contact-search-input, input[placeholder*="Tìm"], input[placeholder*="Search"]').first
        await search_input.click(timeout=5000)
        await search_input.fill("HÀNG QUÁ TRỌNG LƯỢNG")
        await asyncio.sleep(2.0)
        
        group_clicked = await automation.zalo_page.evaluate("""
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
            if progress_callback:
                await progress_callback("Đã chọn nhóm 'HÀNG QUÁ TRỌNG LƯỢNG'. Chờ tải tin nhắn...")
            await asyncio.sleep(3.0)
    except Exception as e:
        print(f"[5-in-1] Lỗi tự động chọn nhóm: {e}")

    # If start_tracking is provided, locate it
    if start_tracking:
        if progress_callback:
            await progress_callback(f"Đang định vị mã mốc {start_tracking}...")
        found = await automation.jump_to_tracking(start_tracking)
        if found:
            if progress_callback:
                await progress_callback(f"Đã định vị thành công mã mốc: {start_tracking}")
            await automation.zalo_page.evaluate("""
                async (trk) => {
                    const chatItems = Array.from(document.querySelectorAll(window.zalo_chat_item || '.chat-item'));
                    const target = chatItems.find(item => (item.innerText || '').includes(trk));
                    if (target) {
                        const scrollContainer = document.querySelector(window.zalo_scroll_container || '.message-view__scroll .transform-gpu') || Array.from(document.querySelectorAll('div')).reduce(function(best,el){var s=window.getComputedStyle(el),r=el.getBoundingClientRect();if((s.overflowY==='scroll'||s.overflowY==='auto')&&r.height>400&&r.width>400&&el.scrollHeight>el.clientHeight+100){if(!best||el.scrollHeight>best.scrollHeight)return el;}return best;},null);
                        if (scrollContainer) {
                            const rect = target.getBoundingClientRect();
                            const containerRect = scrollContainer.getBoundingClientRect();
                            const isVisible = rect.top >= containerRect.top + 80 && rect.bottom <= containerRect.bottom - 80;
                            if (!isVisible) {
                                target.scrollIntoView({ block: 'center' });
                                await new Promise(resolve => setTimeout(resolve, 500));
                            }
                        }
                    }
                }
            """, start_tracking)
        else:
            print(f"[5-in-1] Không tìm thấy mã mốc qua tìm kiếm Zalo. Thử cuộn lên để tìm mốc...")
            if progress_callback:
                await progress_callback(f"Đang cuộn tìm mã mốc {start_tracking} (dự phòng)...")
            found_fallback = await automation.zalo_page.evaluate("""
                async (trk) => {
                    const scrollContainer = document.querySelector(window.zalo_scroll_container || '.message-view__scroll .transform-gpu') || Array.from(document.querySelectorAll('div')).reduce(function(best,el){var s=window.getComputedStyle(el),r=el.getBoundingClientRect();if((s.overflowY==='scroll'||s.overflowY==='auto')&&r.height>400&&r.width>400&&el.scrollHeight>el.clientHeight+100){if(!best||el.scrollHeight>best.scrollHeight)return el;}return best;},null);
                    if (!scrollContainer) return false;
                    const isVisible = () => {
                        const chatItems = Array.from(document.querySelectorAll(window.zalo_chat_item || '.chat-item'));
                        return chatItems.some(item => (item.innerText || '').includes(trk));
                    };
                    if (isVisible()) return true;
                    
                    let lastScrollTop = scrollContainer.scrollTop;
                    for (let i = 0; i < 40; i++) {
                        scrollContainer.scrollTop -= 1000;
                        await new Promise(resolve => setTimeout(resolve, 300));
                        if (isVisible()) return true;
                        if (scrollContainer.scrollTop === lastScrollTop) break;
                        lastScrollTop = scrollContainer.scrollTop;
                    }
                    return false;
                }
            """, start_tracking)
            if found_fallback:
                print(f"[5-in-1] Đã định vị thành công mã mốc {start_tracking} bằng cuộn dự phòng.")
            else:
                print(f"[5-in-1] Không tìm thấy mã mốc {start_tracking} trong DOM. Bắt đầu từ vị trí hiện tại.")
    elif direction == "down":
        if progress_callback:
            await progress_callback("Đang tìm và định vị tin nhắn ghim...")
        print("[5-in-1] Hướng quét xuôi và không có mã mốc. Đang tìm và định vị tin nhắn ghim...")
        resolved_tracking = await automation.resolve_pinned_tracking()
        if resolved_tracking:
            print(f"[5-in-1] Đã định vị tin nhắn ghim thành công. Bắt đầu quét từ mốc: {resolved_tracking}")
            start_tracking = resolved_tracking
            if progress_callback:
                await progress_callback(f"Đã định vị thành công tin nhắn ghim: {resolved_tracking}")
        else:
            print("[5-in-1] Không tìm thấy mốc ghim hợp lệ. Bắt đầu quét từ vị trí hiện tại.")
            if progress_callback:
                await progress_callback("Không tìm thấy tin nhắn ghim. Bắt đầu từ vị trí hiện tại.")
    elif direction == "up":
        # Start from the bottom / newest messages
        print("[5-in-1] Hướng quét ngược: Cuộn xuống dưới cùng để bắt đầu...")
        if progress_callback:
            await progress_callback("Đang cuộn xuống tin nhắn mới nhất...")
        await automation.zalo_page.evaluate("""
            () => {
                const scrollContainer = document.querySelector(window.zalo_scroll_container || '.message-view__scroll .transform-gpu') || Array.from(document.querySelectorAll('div')).reduce(function(best,el){var s=window.getComputedStyle(el),r=el.getBoundingClientRect();if((s.overflowY==='scroll'||s.overflowY==='auto')&&r.height>400&&r.width>400&&el.scrollHeight>el.clientHeight+100){if(!best||el.scrollHeight>best.scrollHeight)return el;}return best;},null);
                if (scrollContainer) {
                    scrollContainer.scrollTop = scrollContainer.scrollHeight;
                }
            }
        """)
        await asyncio.sleep(1.5)

    processed_packages = {}
    processed_trackings = set()
    
    # Load existing scanned list if any
    scanned_path = os.path.join(DATA_DIR, "scanned_packages.json")
    if os.path.exists(scanned_path):
        try:
            with FileLock(scanned_path + '.lock', timeout=5), open(scanned_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
                for item in existing:
                    processed_packages[item["trackingNumber"]] = item
                    if item.get("localStatus") == "Đã tải về":
                        processed_trackings.add(item["trackingNumber"])
        except Exception as e:
            print(f"[5-in-1] Lỗi đọc danh sách cũ: {e}")

    # Maximum folder index currently on disk
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

    # JS helper to retrieve all tracking numbers currently in the DOM
    JS_GET_TRACKINGS = r"""
    (args) => {
        const direction = args ? args.direction || 'up' : 'up';
        const startTrk = args ? args.startTrk : null;
        const allMsgItems = Array.from(document.querySelectorAll(window.zalo_chat_item || '.chat-item'));
        
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
        
        const results = [];
        allMsgItems.forEach((item, idx) => {
            // Apply start tracking filter if active
            if (startIdx !== -1) {
                if (direction === 'up' && idx > startIdx) return;
                if (direction === 'down' && idx < startIdx) return;
            }
            
            const text = (item.innerText || '').trim();
            const matches = text.match(/\b\d{11,12}\b/g) || [];
            const trackingPatterns = text.match(/(?:Mã vận đơn|tracking|mã đơn)\s*:?\s*(\d{11,12})\b/gi) || [];
            const allTrackings = [...new Set([...matches, ...trackingPatterns.map(p => p.match(/\d{11,12}/)).filter(m => m).map(m => m[0])])];
            
            if (allTrackings.length > 0) {
                const isLiked = hasReaction(item);
                
                // Extract weight if any
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
                
                allTrackings.forEach(tr => {
                    results.push({
                        trackingNumber: tr,
                        weight: weight,
                        isLiked: isLiked,
                        domIdx: idx
                    });
                });
            }
        });
        return results;
    }
    """

    JS_GET_SC = """
        () => {
            const sc = document.querySelector(window.zalo_scroll_container || '.message-view__scroll .transform-gpu') ||
                   Array.from(document.querySelectorAll('div')).reduce((best, el) => {
                       const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
                       if ((s.overflowY==='scroll'||s.overflowY==='auto') && r.height>400 && r.width>400 && el.scrollHeight>el.clientHeight+100) {
                           if (!best || el.scrollHeight > best.scrollHeight) return el;
                       }
                       return best;
                   }, null);
            return sc ? { scrollTop: sc.scrollTop, scrollHeight: sc.scrollHeight, clientHeight: sc.clientHeight } : null;
        }
    """

    limit_retry_count = 0
    max_limit_retries = 12   # 12 × 1s = 12 giây chờ Zalo load thêm tin
    last_scroll_height = -1
    last_scroll_top = -1
    stop_scan_now = False

    # ─── SCAN AND PROCESS LOOP ───────────────────────────────────────────
    for step in range(500):
        if automation.stop_requested:
            print("[5-in-1] Dừng quét theo yêu cầu của người dùng.")
            if progress_callback:
                await progress_callback("Đã dừng quét theo yêu cầu của người dùng!")
            automation.stop_requested = False
            break

        if stop_scan_now:
            print("[5-in-1] Dừng quét do đã gặp mốc tin nhắn đã like.")
            if progress_callback:
                await progress_callback("Đã chạm mốc tin nhắn cũ đã xử lý (có tim). Hoàn thành!")
            break

        # 1. Evaluate to get tracking numbers in the current DOM
        results = await automation.zalo_page.evaluate(JS_GET_TRACKINGS, {
            "direction": direction,
            "startTrk": start_tracking
        })
        
        # 2. Sort results based on direction to process in order
        if direction == "up":
            # Scrolling UP: Process from newest (bottom of DOM, highest index) to oldest
            results.sort(key=lambda x: x["domIdx"], reverse=True)
        else:
            # Scrolling DOWN: Process from oldest (top of DOM, lowest index) to newest
            results.sort(key=lambda x: x["domIdx"])

        # 3. Find the first unprocessed target AND check for the boundary
        target_item = None
        consecutive_liked = 0
        for item in results:
            trk = item["trackingNumber"]
            
            if trk in processed_trackings:
                continue
                
            if item["isLiked"]:
                consecutive_liked += 1
                if consecutive_liked >= 3:
                    print(f"[5-in-1] Đã gặp 3 đơn liên tiếp ({trk}) đã được like từ trước. Dừng quét!")
                    stop_scan_now = True
                    break
                continue
            else:
                consecutive_liked = 0
            
            target_item = item
            break

        if stop_scan_now:
            continue

        # 4. If target found, process it one-by-one
        if target_item:
            trk = target_item["trackingNumber"]
            print(f"[5-in-1] ▶ Phát hiện đơn chưa xử lý: {trk}")
            if progress_callback:
                await progress_callback(f"Đang tải đơn {trk}...")

            # Step A: Tag and scroll the bubble into center view
            await automation.zalo_page.evaluate("""
                (args) => {
                    const trk = args.trk;
                    const domIdx = args.domIdx;
                    const chatItems = Array.from(document.querySelectorAll(window.zalo_chat_item || '.chat-item'));
                    const target = chatItems[domIdx];
                    document.querySelectorAll('.zalo-text-target-bubble').forEach(e => e.classList.remove('zalo-text-target-bubble'));
                    if (target) {
                        target.classList.add('zalo-text-target-bubble');
                        target.scrollIntoView({ block: 'center', inline: 'nearest' });
                    }
                }
            """, {"trk": trk, "domIdx": target_item["domIdx"]})
            await asyncio.sleep(0.8)

            max_folder_idx += 1
            folder_name = str(max_folder_idx)
            download_ok = False

            try:
                # Download package media
                imgs, vids = await automation.download_package_media(
                    {"trackingNumber": trk, "weight": target_item["weight"]},
                    pkg_index=folder_name,
                    progress_callback=progress_callback,
                    skip_banner_click=True,
                    skip_scroll_search=False,
                    reverse_scan=(direction == "up")
                )

                # Restore scroll position by centering the active target bubble
                await automation.zalo_page.evaluate("""
                    () => {
                        const target = document.querySelector('.zalo-text-target-bubble');
                        if (target) {
                            target.scrollIntoView({ block: 'center', inline: 'nearest' });
                        }
                    }
                """)
                await asyncio.sleep(0.5)

                local_images = [f"/data/{folder_name}/{os.path.basename(i)}" for i in imgs]
                local_videos = [f"/data/{folder_name}/{os.path.basename(v)}" for v in vids]

                if len(imgs) >= 1 and len(vids) >= 1:
                    processed_packages[trk] = {
                        "trackingNumber": trk,
                        "weight": target_item["weight"],
                        "images": local_images,
                        "videos": local_videos,
                        "folderName": folder_name,
                        "localStatus": "Đã tải về",
                        "jmsStatus": "Chưa xử lý"
                    }
                    processed_trackings.add(trk)
                    download_ok = True
                    print(f"[5-in-1] ✅ Tải xong đơn {trk}")
                else:
                    processed_packages[trk] = {
                        "trackingNumber": trk,
                        "weight": target_item["weight"],
                        "images": local_images,
                        "videos": local_videos,
                        "folderName": folder_name,
                        "localStatus": f"Lỗi: Có {len(imgs)} ảnh, {len(vids)} video (Cần tối thiểu 1 ảnh & 1 video)",
                        "jmsStatus": "Chưa xử lý"
                    }
                    processed_trackings.add(trk)
                    download_ok = False
                    print(f"[5-in-1] ❌ Tải lỗi/thiếu file cho đơn {trk}: Có {len(imgs)} ảnh, {len(vids)} video")

                try:
                    with FileLock(scanned_path + '.lock', timeout=5):
                        disk_pkgs = []
                        if os.path.exists(scanned_path):
                            try:
                                with open(scanned_path, "r", encoding="utf-8") as rf:
                                    disk_pkgs = json.load(rf)
                            except Exception:
                                pass
                        
                        disk_map = {p["trackingNumber"]: p for p in disk_pkgs if isinstance(p, dict) and p.get("trackingNumber")}
                        
                        # Merge in-memory processed_packages with disk packages
                        for t_id, mem_pkg in processed_packages.items():
                            if t_id in disk_map:
                                disk_pkg = disk_map[t_id]
                                if "copied" in disk_pkg and "copied" not in mem_pkg:
                                    mem_pkg["copied"] = disk_pkg["copied"]
                                if disk_pkg.get("copied") and not mem_pkg.get("copied"):
                                    mem_pkg["copied"] = True
                                if disk_pkg.get("jmsStatus") and disk_pkg.get("jmsStatus") != "Chưa xử lý":
                                    mem_pkg["jmsStatus"] = disk_pkg["jmsStatus"]
                        
                        # Preserve packages that exist on disk but not in in-memory dict
                        for t_id, disk_pkg in disk_map.items():
                            if t_id not in processed_packages:
                                processed_packages[t_id] = disk_pkg

                        with open(scanned_path, "w", encoding="utf-8") as f:
                            json.dump(list(processed_packages.values()), f, ensure_ascii=False, indent=4)
                except Exception as we:
                    print(f"[5-in-1] Lỗi ghi file scanned_packages.json: {we}")

            except Exception as dl_err:
                print(f"[5-in-1] ❌ Lỗi tải đơn {trk}: {dl_err}")
                processed_trackings.add(trk)

            # Step B: Apply Like (❤️ Thả tim) to the tracking bubble
            if download_ok:
                try:
                    if progress_callback:
                        await progress_callback(f"Đang thả tim đơn {trk}...")
                    
                    like_res = await automation.zalo_page.evaluate("""
                        async (trk) => {
                            const items = Array.from(document.querySelectorAll(window.zalo_chat_item || '.chat-item'));
                            const target = items.find(el => (el.innerText||'').includes(trk));
                            if (!target) return { success: false, error: 'Không tìm thấy bong bóng tin nhắn trong DOM' };
                            
                            target.scrollIntoView({ block: 'center', inline: 'nearest' });
                            await new Promise(resolve => setTimeout(resolve, 300));
                            
                            // Check if already liked
                            const sp = target.querySelector(window.zalo_reaction_space || '.message-reaction-v2-space');
                            if (sp && sp.getBoundingClientRect().height > 0) {
                                return { success: true, alreadyLiked: true };
                            }
                            
                            // Programmatically dispatch hover events to trigger reaction popup
                            const hoverEl = target.querySelector('.message-frame, .message-non-frame, .message-content-render') || target;
                            const rect = hoverEl.getBoundingClientRect();
                            hoverEl.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true, clientX: rect.left + rect.width/2, clientY: rect.top + rect.height/2 }));
                            hoverEl.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, clientX: rect.left + rect.width/2, clientY: rect.top + rect.height/2 }));
                            
                            // Wait for the reaction heart icon (.default-react-icon-thumb) to appear
                            for (let i = 0; i < 15; i++) {
                                await new Promise(resolve => setTimeout(resolve, 100));
                                const thumb = target.querySelector('.default-react-icon-thumb');
                                if (thumb && thumb.getBoundingClientRect().width > 0) {
                                    thumb.click();
                                    await new Promise(resolve => setTimeout(resolve, 300));
                                    return { success: true, alreadyLiked: false };
                                }
                            }
                            
                            // Fallback click on any reaction button in the bubble
                            const anyReactBtn = target.querySelector('[class*="react"], [class*="like"], [class*="thumb"]');
                            if (anyReactBtn && anyReactBtn.getBoundingClientRect().width > 0) {
                                anyReactBtn.click();
                                await new Promise(resolve => setTimeout(resolve, 300));
                                return { success: true, fallbackClicked: true };
                            }
                            
                            return { success: false, error: 'Không tìm thấy nút Thả tim mặc định' };
                        }
                    """, trk)
                    
                    if like_res and like_res.get("success"):
                        if like_res.get("alreadyLiked"):
                            print(f"[5-in-1] Đơn {trk} đã có tim.")
                        else:
                            print(f"[5-in-1] ❤️ Đã thả tim đơn {trk}")
                    else:
                        print(f"[5-in-1] ⚠️ Không tim được đơn {trk}: {like_res.get('error') if like_res else 'unknown'}")
                    
                    await asyncio.sleep(0.4)
                except Exception as le:
                    print(f"[5-in-1] Lỗi thả tim đơn {trk}: {le}")

            # Step C: Scroll a small amount in specified direction after processing each single bill
            scroll_amount_single = 300
            print(f"[5-in-1] Xử lý xong đơn {trk} → Cuộn {'lên' if direction == 'up' else 'xuống'} {scroll_amount_single}px")
            try:
                await automation.zalo_page.evaluate("""
                    (args) => {
                        const amt = args.amt;
                        const dir = args.dir;
                        const sc = document.querySelector(window.zalo_scroll_container || '.message-view__scroll .transform-gpu') ||
                               Array.from(document.querySelectorAll('div')).reduce((best, el) => {
                                   const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
                                   if ((s.overflowY==='scroll'||s.overflowY==='auto') && r.height>400 && r.width>400 && el.scrollHeight>el.clientHeight+100) {
                                       if (!best || el.scrollHeight > best.scrollHeight) return el;
                                   }
                                   return best;
                               }, null);
                        if (sc) {
                            if (dir === 'up') {
                                if (sc.scrollTop <= 5) {
                                    sc.scrollTop = 15;
                                    sc.dispatchEvent(new Event('scroll', { bubbles: true }));
                                    sc.scrollTop = 0;
                                } else {
                                    sc.scrollTop -= amt;
                                }
                            } else {
                                sc.scrollTop += amt;
                            }
                            sc.dispatchEvent(new Event('scroll', { bubbles: true }));
                            const delta = dir === 'up' ? -amt : amt;
                            sc.dispatchEvent(new WheelEvent('wheel', { deltaY: delta, bubbles: true }));
                        }
                    }
                """, {"amt": scroll_amount_single, "dir": direction})
                await asyncio.sleep(1.0) # Wait for Zalo to lazy-load older messages
            except Exception as se:
                print(f"[5-in-1] Lỗi cuộn sau khi xử lý đơn {trk}: {se}")

            # Loop back immediately to check DOM
            continue

        # 5. If no unprocessed target exists in the current DOM, scroll in the specified direction
        sinfo = await automation.zalo_page.evaluate(JS_GET_SC)
        if not sinfo:
            print("[5-in-1] Không tìm thấy khung cuộn tin nhắn Zalo.")
            break

        cur_top = sinfo["scrollTop"]
        cur_height = sinfo["scrollHeight"]
        cur_client = sinfo["clientHeight"]

        if direction == "up":
            at_boundary = (cur_top <= 5)
        else:
            at_boundary = (cur_top + cur_client >= cur_height - 15)

        if at_boundary:
            if cur_height == last_scroll_height and cur_top == last_scroll_top:
                limit_retry_count += 1
                print(f"[5-in-1] Chờ Zalo load thêm tin ({limit_retry_count}/{max_limit_retries})...")
                if progress_callback:
                    await progress_callback(f"Chờ tải thêm tin ({limit_retry_count}/{max_limit_retries})...")
                if limit_retry_count >= max_limit_retries:
                    print("[5-in-1] Đã đạt biên giới chat và không còn tin nhắn mới. Hoàn thành quét.")
                    break
                await asyncio.sleep(1.0)
                continue
            else:
                limit_retry_count = 0
        else:
            limit_retry_count = 0

        last_scroll_top = cur_top
        last_scroll_height = cur_height

        scroll_amount = 500
        print(f"[5-in-1] Không có đơn chưa xử lý trong view → cuộn {'lên' if direction == 'up' else 'xuống'} {scroll_amount}px")
        if progress_callback:
            await progress_callback("Đang cuộn tìm tin nhắn cũ...")

        await automation.zalo_page.evaluate("""
            (args) => {
                const amt = args.amt;
                const dir = args.dir;
                const sc = document.querySelector(window.zalo_scroll_container || '.message-view__scroll .transform-gpu') ||
                       Array.from(document.querySelectorAll('div')).reduce((best, el) => {
                           const s = window.getComputedStyle(el), r = el.getBoundingClientRect();
                           if ((s.overflowY==='scroll'||s.overflowY==='auto') && r.height>400 && r.width>400 && el.scrollHeight>el.clientHeight+100) {
                               if (!best || el.scrollHeight > best.scrollHeight) return el;
                           }
                           return best;
                           }, null);
                if (sc) {
                    if (dir === 'up') {
                        if (sc.scrollTop <= 5) {
                            sc.scrollTop = 15;
                            sc.dispatchEvent(new Event('scroll', { bubbles: true }));
                            sc.scrollTop = 0;
                        } else {
                            sc.scrollTop -= amt;
                        }
                    } else {
                        sc.scrollTop += amt;
                    }
                    sc.dispatchEvent(new Event('scroll', { bubbles: true }));
                    const delta = dir === 'up' ? -amt : amt;
                    sc.dispatchEvent(new WheelEvent('wheel', { deltaY: delta, bubbles: true }));
                }
            }
        """, {"amt": scroll_amount, "dir": direction})
        await asyncio.sleep(1.5)

    return sorted(list(processed_packages.values()), key=lambda x: x["trackingNumber"])
