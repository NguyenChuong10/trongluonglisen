import os
import re

file_path = "backend/automation.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# I will define the new search logic exactly as planned
new_search = r"""                        // 3. Bi-directional Search for Media
                        let pinnedIdx = typeof pinnedIdx !== 'undefined' ? pinnedIdx : -1;
                        textBubbles.forEach(anchor => {
                            let candidates = [];
                            
                            // Scan UP
                            for (let i = anchor.idx - 1; i >= 0; i--) {
                                if (pinnedIdx !== -1 && i < pinnedIdx) break;
                                const neighbor = allMsgItems[i];
                                if (isRecalled(neighbor)) continue;
                                if (neighbor.sender !== anchor.sender) break;
                                
                                const text = neighbor.innerText || '';
                                const neighborTrks = [...(text.match(/\b\d{11,12}\b/g) || []), ...(text.match(/(?:Mã vận đơn|tracking|mã đơn)\s*:?\s*(\d{11,12})\b/gi) || []).map(p=>p.match(/\d{11,12}/)).filter(m=>m).map(m=>m[0])];
                                if (neighborTrks.length > 0) break;
                                
                                const imgs = getImagesInItem(neighbor);
                                const vids = getVideosInItem(neighbor);
                                if (imgs.length > 0 || vids.length > 0) {
                                    candidates.push({
                                        idx: i,
                                        distance: Math.abs(anchor.idx - i),
                                        images: imgs.filter(url => !vids.includes(url)),
                                        videos: vids
                                    });
                                }
                            }
                            
                            // Scan DOWN
                            for (let i = anchor.idx + 1; i < allMsgItems.length; i++) {
                                const neighbor = allMsgItems[i];
                                if (isRecalled(neighbor)) continue;
                                if (neighbor.sender !== anchor.sender) break;
                                
                                const text = neighbor.innerText || '';
                                const neighborTrks = [...(text.match(/\b\d{11,12}\b/g) || []), ...(text.match(/(?:Mã vận đơn|tracking|mã đơn)\s*:?\s*(\d{11,12})\b/gi) || []).map(p=>p.match(/\d{11,12}/)).filter(m=>m).map(m=>m[0])];
                                if (neighborTrks.length > 0) break;
                                
                                const imgs = getImagesInItem(neighbor);
                                const vids = getVideosInItem(neighbor);
                                if (imgs.length > 0 || vids.length > 0) {
                                    candidates.push({
                                        idx: i,
                                        distance: Math.abs(anchor.idx - i),
                                        images: imgs.filter(url => !vids.includes(url)),
                                        videos: vids
                                    });
                                }
                            }
                            
                            // Sort candidates by distance (closest first)
                            candidates.sort((a, b) => a.distance - b.distance);
                            
                            // Now take up to 3 images and up to 1 video
                            let selectedImages = [];
                            let selectedVideos = [];
                            let selectedIndices = new Set();
                            
                            for (const c of candidates) {
                                let used = false;
                                // Take videos
                                for (const v of c.videos) {
                                    if (selectedVideos.length < 1) { // MAX 1 VIDEO
                                        selectedVideos.push(v);
                                        used = true;
                                    }
                                }
                                // Take images
                                for (const img of c.images) {
                                    if (selectedImages.length < 3) { // MAX 3 IMAGES
                                        selectedImages.push(img);
                                        used = true;
                                    }
                                }
                                if (used) {
                                    selectedIndices.add(c.idx);
                                }
                                
                                if (selectedImages.length >= 3 && selectedVideos.length >= 1) {
                                    break; // We have exactly what we need!
                                }
                            }
                            
                            anchor.images = selectedImages;
                            anchor.videos = selectedVideos;
                            anchor.assignedMediaIndices = Array.from(selectedIndices).sort((a,b) => a - b);
                        });"""

# Because it appears 3 times, we will replace all 3 occurrences.
content_new = re.sub(
    r'                        // 3\. Bi-directional Search for Media.*?assignedMediaIndices = \[\.\.\.new Set\(anchor\.assignedMediaIndices\)\]\.sort\(\(a,b\) => a - b\);\n                        \}\);', 
    lambda m: new_search, 
    content, 
    flags=re.DOTALL
)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content_new)

print("Replaced occurrences of the logic.")
