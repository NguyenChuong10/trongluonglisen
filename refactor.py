import os
import re

file_path = "backend/automation.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. We want to replace the `js_scraper` block from `js_scraper = r"""` to `"""` (around lines 668-1075)
# 2. We want to replace the `marker_result = await self.zalo_page.evaluate(r"""` to `"""` (around lines 1310-1590)

js_algo = r"""
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
                item.sender = currentSender;
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

            // 3. Bi-directional Search for Media
            textBubbles.forEach(anchor => {
                // Scan UP
                for (let i = anchor.idx - 1; i >= 0; i--) {
                    if (pinnedIdx !== -1 && i < pinnedIdx) break; // Don't scan above pinned
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
                        anchor.images.push(...imgs.filter(url => !vids.includes(url)));
                        anchor.videos.push(...vids);
                    }
                }
                
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
                        anchor.images.push(...imgs.filter(url => !vids.includes(url)));
                        anchor.videos.push(...vids);
                    }
                }
                
                // Deduplicate and Sort
                anchor.images = [...new Set(anchor.images)];
                anchor.videos = [...new Set(anchor.videos)];
                anchor.assignedMediaIndices = [...new Set(anchor.assignedMediaIndices)].sort((a,b) => a - b);
            });
"""

# Regex matching blocks
scraper_pattern = re.compile(r'js_scraper = r"""\n        \(args\) => \{.*?\n        \}\n        """', re.DOTALL)
marker_pattern = re.compile(r'marker_result = await self.zalo_page.evaluate\(r"""\n            async \(\{ trackingNumber, skipScrollSearch \}\) => \{.*?            \}\n        """,', re.DOTALL)

# Reconstruct js_scraper
new_js_scraper = f'''js_scraper = r"""
        (args) => {{
            const pinnedTrk = args ? args.pinnedTrk : null;
            const direction = args ? args.direction || 'down' : 'down';
            const startTrk = args ? args.startTrk : null;
            const allMsgItems = Array.from(document.querySelectorAll(window.zalo_chat_item || '.chat-item'));
            
            let pinnedIdx = -1;
            if (pinnedTrk) {{
                pinnedIdx = allMsgItems.findIndex(item => (item.innerText || '').includes(pinnedTrk));
            }}
            
            let startIdx = -1;
            if (startTrk) {{
                startIdx = allMsgItems.findIndex(item => (item.innerText || '').includes(startTrk));
            }}
            
            const hasReaction = (item) => {{
                const v2space = item.querySelector(window.zalo_reaction_space || '.message-reaction-v2-space');
                if (v2space) {{
                    const rect = v2space.getBoundingClientRect();
                    if (rect.height > 0) return true;
                }}
                return false;
            }};
{js_algo}

            // Determine stop boundaries
            let stopScan = false;
            let reactionIdx = -1;
            
            const isPackageComponent = (idx) => {{
                for (const tb of textBubbles) {{
                    if (tb.idx === idx || (tb.assignedMediaIndices && tb.assignedMediaIndices.includes(idx))) return true;
                }}
                return false;
            }};

            if (direction === 'up') {{
                for (let i = allMsgItems.length - 1; i >= 0; i--) {{
                    if (startIdx !== -1 && i >= startIdx) continue;
                    if (hasReaction(allMsgItems[i]) && isPackageComponent(i)) {{
                        reactionIdx = i;
                        stopScan = true;
                        break;
                    }}
                }}
            }} else if (direction === 'down') {{
                for (let i = 0; i < allMsgItems.length; i++) {{
                    if (startIdx !== -1 && i <= startIdx) continue;
                    if (hasReaction(allMsgItems[i]) && isPackageComponent(i)) {{
                        reactionIdx = i;
                        stopScan = true;
                        break;
                    }}
                }}
            }}

            const viewPackages = [];
            textBubbles.forEach(text => {{
                if (pinnedIdx !== -1 && text.idx < pinnedIdx) return;
                if (startIdx !== -1) {{
                    if (direction === 'up' && text.idx > startIdx) return;
                    if (direction === 'down' && text.idx < startIdx) return;
                }}
                
                if (direction === 'up') {{
                    if (reactionIdx !== -1 && text.idx <= reactionIdx) return;
                }} else {{
                    if (reactionIdx !== -1 && text.idx >= reactionIdx) return;
                }}
                
                if (text.hasReaction) return;
                
                if (true) {{ // Capture all packages regardless of media rendering status during scan
                    let mediaHasReaction = false;
                    for (let mediaIdx of text.assignedMediaIndices) {{
                        if (direction === 'up' && reactionIdx !== -1 && mediaIdx <= reactionIdx) mediaHasReaction = true;
                        if (direction === 'down' && reactionIdx !== -1 && mediaIdx >= reactionIdx) mediaHasReaction = true;
                        if (hasReaction(allMsgItems[mediaIdx])) mediaHasReaction = true;
                    }}
                    if (mediaHasReaction) return;

                    text.trackingNumbers.forEach(trackingNumber => {{
                        if (!viewPackages.some(p => p.trackingNumber === trackingNumber)) {{
                            viewPackages.push({{
                                trackingNumber,
                                weight: text.weight,
                                images: text.images,
                                videos: text.videos
                            }});
                        }}
                    }});
                }}
            }});
            
            return {{
                packages: viewPackages,
                stopScan: stopScan
            }};
        }}
        """'''

# Reconstruct marker_result
new_marker_result = f'''marker_result = await self.zalo_page.evaluate(r"""
            async ({{ trackingNumber, skipScrollSearch }}) => {{
                try {{
                    const scrollContainer = document.querySelector('.message-view__scroll .transform-gpu, #messageViewContainer .transform-gpu, .transform-gpu') || Array.from(document.querySelectorAll('div')).reduce(function(best,el){{var s=window.getComputedStyle(el),r=el.getBoundingClientRect();if((s.overflowY==='scroll'||s.overflowY==='auto')&&r.height>400&&r.width>400&&el.scrollHeight>el.clientHeight+100){{if(!best||el.scrollHeight>best.scrollHeight)return el;}}return best;}},null);
                    if (!scrollContainer) return {{ success: false, error: 'Không tìm thấy khung cuộn chat Zalo.' }};
                    const allMsgItems = Array.from(document.querySelectorAll(window.zalo_chat_item || '.chat-item'));
                    let pinnedIdx = -1;
                    
                    const hasReaction = (item) => {{
                        const v2space = item.querySelector(window.zalo_reaction_space || '.message-reaction-v2-space');
                        if (v2space) {{
                            const rect = v2space.getBoundingClientRect();
                            if (rect.height > 0) return true;
                        }}
                        return false;
                    }};
{js_algo}
                    
                    const targetTb = textBubbles.find(tb => tb.trackingNumbers.includes(trackingNumber));
                    if (!targetTb) return null;
                    
                    document.querySelectorAll('.zalo-text-target-bubble').forEach(el => el.classList.remove('zalo-text-target-bubble'));
                    allMsgItems[targetTb.idx].classList.add('zalo-text-target-bubble');
                    
                    document.querySelectorAll('.zalo-video-temp-target').forEach(el => el.classList.remove('zalo-video-temp-target'));
                    document.querySelectorAll('[class*="zalo-target-bubble-"]').forEach(el => {{
                        Array.from(el.classList).forEach(c => {{
                            if (c.startsWith('zalo-target-bubble-')) el.classList.remove(c);
                        }});
                    }});
                    
                    if (targetTb.assignedMediaIndices && targetTb.assignedMediaIndices.length > 0) {{
                        targetTb.assignedMediaIndices.forEach((idx, order) => {{
                            allMsgItems[idx].classList.add(`zalo-target-bubble-${{order}}`);
                        }});
                        return {{ firstBubble: allMsgItems[targetTb.assignedMediaIndices[0]], count: targetTb.assignedMediaIndices.length }};
                    }}
                    return {{ firstBubble: allMsgItems[targetTb.idx], count: 1 }};
                }} catch (e) {{
                    return {{ success: false, error: e.toString() }};
                }}
            }}
        """, {{"trackingNumber": trackingNumber, "skipScrollSearch": skipScrollSearch}})'''

content_new = scraper_pattern.sub(new_js_scraper.replace('\\', '\\\\'), content, count=1)
content_new = marker_pattern.sub(new_marker_result.replace('\\', '\\\\') + ',', content_new, count=1)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content_new)

print("Refactored backend/automation.py")
