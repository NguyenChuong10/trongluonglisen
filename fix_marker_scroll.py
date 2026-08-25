import os
import re

file_path = "backend/automation.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

bad_str_1 = """                    if (targetTb.assignedMediaIndices && targetTb.assignedMediaIndices.length > 0) {
                        targetTb.assignedMediaIndices.forEach((idx, order) => {
                            allMsgItems[idx].classList.add(`zalo-target-bubble-${order}`);
                        });
                        return { firstBubble: allMsgItems[targetTb.assignedMediaIndices[0]], count: targetTb.assignedMediaIndices.length };
                    }
                    return { firstBubble: allMsgItems[targetTb.idx], count: 1 };"""

good_str_1 = """                    let firstBubble = null;
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
                    
                    return { success: true, count: count };"""

content = content.replace(bad_str_1, good_str_1)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed scroll in marker result")
