// Global Claiming Algorithm logic structure
const textBubbles = []; // anchors
const mediaItems = [];

// For each mediaItem, find closest valid anchor
mediaItems.forEach(media => {
    let closestAnchor = null;
    let minDistance = Infinity;
    
    textBubbles.forEach(anchor => {
        if (anchor.sender !== media.sender) return; // Boundary 1: Sender
        
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
            // Tie-breaker: If distance is equal, prefer the anchor that comes BEFORE the media.
            // (e.g. Text then Media is more common than Media then Text? Actually, either is fine. We can just pick the first one).
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

// Then for each anchor, sort candidates by distance and take 3 imgs, 1 vid
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
});
