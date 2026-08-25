import os
import re

file_path = "backend/automation.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# I will replace the content of `tag_success` script
# Wait, I can just replace from `tag_success = await self.zalo_page.evaluate(r"""`
# to `""", {"trackingNumber": tracking_number, "bubbleIdx": bubble_idx})`

pattern = re.compile(r'tag_success = await self\.zalo_page\.evaluate\(r"""\n                async \(\{ trackingNumber, bubbleIdx \}\) => \{.*?""", \{"trackingNumber": tracking_number, "bubbleIdx": bubble_idx\}\)', re.DOTALL)

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
                        let pinnedIdx = -1; // Assuming we don't care about pinned for tagging locally inside loop, or we can just ignore it.
                        textBubbles.forEach(anchor => {
                            // Scan UP
                            for (let i = anchor.idx - 1; i >= 0; i--) {
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
                            
                            // Deduplicate and Sort
                            anchor.assignedMediaIndices = [...new Set(anchor.assignedMediaIndices)].sort((a,b) => a - b);
                        });
"""

replacement = f'''tag_success = await self.zalo_page.evaluate(r"""
                async ({{ trackingNumber, bubbleIdx }}) => {{
                    try {{
                        const allMsgItems = Array.from(document.querySelectorAll(window.zalo_chat_item || '.chat-item'));
                        
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
                        if (!targetTb) return {{ success: false, error: 'Không tìm thấy tin nhắn chứa mã.' }};
                        
                        document.querySelectorAll('.zalo-text-target-bubble').forEach(el => el.classList.remove('zalo-text-target-bubble'));
                        allMsgItems[targetTb.idx].classList.add('zalo-text-target-bubble');
                        
                        document.querySelectorAll('.zalo-video-temp-target').forEach(el => el.classList.remove('zalo-video-temp-target'));
                        document.querySelectorAll('[class*="zalo-target-bubble-"]').forEach(el => {{
                            Array.from(el.classList).forEach(c => {{
                                if (c.startsWith('zalo-target-bubble-')) el.classList.remove(c);
                            }});
                        }});
                        
                        let targetBubble = null;
                        if (targetTb.assignedMediaIndices && targetTb.assignedMediaIndices.length > 0) {{
                            if (bubbleIdx < targetTb.assignedMediaIndices.length) {{
                                targetBubble = allMsgItems[targetTb.assignedMediaIndices[bubbleIdx]];
                                targetBubble.classList.add(`zalo-target-bubble-${{bubbleIdx}}`);
                            }}
                        }} else {{
                            if (bubbleIdx === 0) {{
                                targetBubble = allMsgItems[targetTb.idx];
                            }}
                        }}
                        
                        if (targetBubble) {{
                            targetBubble.scrollIntoView({{ block: 'center' }});
                            return {{ success: true }};
                        }}
                        
                        return {{ success: false, error: 'Không tìm thấy media bubble tương ứng với bubbleIdx.' }};
                    }} catch (e) {{
                        return {{ success: false, error: e.toString() }};
                    }}
                }}
            """, {{"trackingNumber": tracking_number, "bubbleIdx": bubble_idx}})'''

content_new = pattern.sub(replacement.replace('\\', '\\\\'), content)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content_new)

print("Done tag_success replacement")
