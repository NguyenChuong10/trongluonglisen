import os
import re

file_path = "backend/automation.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

new_search = r"""                        // 3. Exclusive Closest Media Search
                        let pinnedIdx = typeof pinnedIdx !== 'undefined' ? pinnedIdx : -1;
                        
                        const mediaItems = [];
                        allMsgItems.forEach((item, i) => {
                            if (pinnedIdx !== -1 && i < pinnedIdx) return;
                            if (isRecalled(item)) return;
                            
                            const imgs = getImagesInItem(item);
                            const vids = getVideosInItem(item);
                            if (imgs.length > 0 || vids.length > 0) {
                                mediaItems.push({
                                    idx: i,
                                    sender: item.sender,
                                    images: imgs.filter(url => !vids.includes(url)),
                                    videos: vids
                                });
                            }
                        });
                        
                        textBubbles.forEach(tb => {
                            tb.candidateMedia = [];
                        });
                        
                        mediaItems.forEach(media => {
                            let closestAnchor = null;
                            let minDistance = Infinity;
                            
                            textBubbles.forEach(anchor => {
                                if (anchor.sender !== media.sender) return; // Boundary 1: Different Sender
                                
                                // Boundary 2: No anchor crossed
                                const minIdx = Math.min(anchor.idx, media.idx);
                                const maxIdx = Math.max(anchor.idx, media.idx);
                                let crossed = false;
                                textBubbles.forEach(other => {
                                    if (other.idx > minIdx && other.idx < maxIdx) {
                                        crossed = true;
                                    }
                                });
                                if (crossed) return;
                                
                                const dist = Math.abs(anchor.idx - media.idx);
                                if (dist < minDistance) {
                                    minDistance = dist;
                                    closestAnchor = anchor;
                                } else if (dist === minDistance) {
                                    if (anchor.idx < media.idx) {
                                        closestAnchor = anchor;
                                    }
                                }
                            });
                            
                            if (closestAnchor) {
                                closestAnchor.candidateMedia.push({
                                    idx: media.idx,
                                    distance: minDistance,
                                    images: media.images,
                                    videos: media.videos
                                });
                            }
                        });
                        
                        textBubbles.forEach(anchor => {
                            anchor.candidateMedia.sort((a, b) => a.distance - b.distance);
                            
                            let selectedIndices = new Set();
                            let imgCount = 0;
                            let vidCount = 0;
                            
                            for (const c of anchor.candidateMedia) {
                                let used = false;
                                
                                if (vidCount < 1 && c.videos.length > 0) {
                                    vidCount += c.videos.length;
                                    used = true;
                                }
                                
                                if (imgCount < 3 && c.images.length > 0) {
                                    imgCount += c.images.length;
                                    used = true;
                                }
                                
                                if (used) {
                                    selectedIndices.add(c.idx);
                                }
                                
                                if (imgCount >= 3 && vidCount >= 1) {
                                    break;
                                }
                            }
                            
                            anchor.assignedMediaIndices = Array.from(selectedIndices).sort((a, b) => a - b);
                        });"""

content_new = re.sub(
    r'                        // 3\. Bi-directional Search for Media.*?assignedMediaIndices = Array\.from\(selectedIndices\)\.sort\(\(a,b\) => a - b\);\n                        \}\);', 
    lambda m: new_search, 
    content, 
    flags=re.DOTALL
)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content_new)

print("Replaced occurrences of the logic.")
