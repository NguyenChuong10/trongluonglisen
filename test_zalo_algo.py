import sys
import asyncio
import os
import json
from playwright.async_api import async_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

html_content = """
<!DOCTYPE html>
<html>
<head><style>
.chat-item { border: 1px solid #ccc; margin: 5px; padding: 5px; }
.avatar { width: 40px; height: 40px; }
.card-send { background: #e0f7fa; }
img { display: block; margin: 5px; }
.video { width: 200px; height: 150px; background: black; color: white; display:flex; align-items:center; justify-content:center; }
</style></head>
<body>

<!-- User A: Case 1: Standard -->
<div class="chat-item">
    <img src="ava1.jpg" class="avatar">
    <img src="img1_1.jpg" style="width:100px;height:100px" data-src="img1_1.jpg">
    <img src="img1_2.jpg" style="width:100px;height:100px" data-src="img1_2.jpg">
    <img src="img1_3.jpg" style="width:100px;height:100px" data-src="img1_3.jpg">
    <div class="video">Video 1</div>
</div>
<div class="chat-item">
    <img src="ava1.jpg" class="avatar">
    Mã vận đơn: 111111111111 2.5kg
</div>

<!-- User B: Case 2: Images -> Text -> Video -->
<div class="chat-item">
    <img src="ava2.jpg" class="avatar">
    <img src="img2_1.jpg" style="width:100px;height:100px" data-src="img2_1.jpg">
    <img src="img2_2.jpg" style="width:100px;height:100px" data-src="img2_2.jpg">
    <img src="img2_3.jpg" style="width:100px;height:100px" data-src="img2_3.jpg">
</div>
<div class="chat-item">
    <img src="ava2.jpg" class="avatar">
    Mã vận đơn: 222222222222 1,8kg
</div>
<div class="chat-item">
    <img src="ava2.jpg" class="avatar">
    <div class="video">Video 2</div>
</div>

<!-- User A: Case 3: Interrupted by recalled -->
<div class="chat-item">
    <img src="ava1.jpg" class="avatar">
    <img src="img3_1.jpg" style="width:100px;height:100px" data-src="img3_1.jpg">
    <img src="img3_2.jpg" style="width:100px;height:100px" data-src="img3_2.jpg">
</div>
<div class="chat-item">
    <img src="ava1.jpg" class="avatar">
    Đã thu hồi tin nhắn
</div>
<div class="chat-item">
    <img src="ava1.jpg" class="avatar">
    <img src="img3_3.jpg" style="width:100px;height:100px" data-src="img3_3.jpg">
    <div class="video">Video 3</div>
</div>
<div class="chat-item">
    <img src="ava1.jpg" class="avatar">
    333333333333
</div>

<!-- User C: Case 4: Scattered -->
<div class="chat-item">
    <img src="ava3.jpg" class="avatar">
    <img src="img4_1.jpg" style="width:100px;height:100px" data-src="img4_1.jpg">
</div>
<div class="chat-item">
    <img src="ava3.jpg" class="avatar">
    <img src="img4_2.jpg" style="width:100px;height:100px" data-src="img4_2.jpg">
</div>
<div class="chat-item">
    <img src="ava3.jpg" class="avatar">
    <img src="img4_3.jpg" style="width:100px;height:100px" data-src="img4_3.jpg">
</div>
<div class="chat-item">
    <img src="ava3.jpg" class="avatar">
    <div class="video">Video 4</div>
</div>
<div class="chat-item">
    <img src="ava3.jpg" class="avatar">
    Mã vận đơn 444444444444 3kg
</div>

<!-- User A: Case 5: Text then Media -->
<div class="chat-item">
    <img src="ava1.jpg" class="avatar">
    Tracking: 555555555555 4kg
</div>
<div class="chat-item">
    <img src="ava1.jpg" class="avatar">
    <img src="img5_1.jpg" style="width:100px;height:100px" data-src="img5_1.jpg">
    <img src="img5_2.jpg" style="width:100px;height:100px" data-src="img5_2.jpg">
</div>
<div class="chat-item">
    <img src="ava1.jpg" class="avatar">
    <div class="video">Video 5</div>
    <img src="img5_3.jpg" style="width:100px;height:100px" data-src="img5_3.jpg">
</div>

<!-- User A: Case 6: Transition standard immediately after Case 5 -->
<div class="chat-item">
    <img src="ava1.jpg" class="avatar">
    <img src="img6_1.jpg" style="width:100px;height:100px" data-src="img6_1.jpg">
    <img src="img6_2.jpg" style="width:100px;height:100px" data-src="img6_2.jpg">
    <img src="img6_3.jpg" style="width:100px;height:100px" data-src="img6_3.jpg">
    <div class="video">Video 6</div>
</div>
<div class="chat-item">
    <img src="ava1.jpg" class="avatar">
    Mã vận đơn: 666666666666 2.5kg
</div>

</body>
</html>

"""

with open("zalo_mock.html", "w", encoding="utf-8") as f:
    f.write(html_content)

async def run_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Load the mock HTML
        file_path = "file://" + os.path.abspath("zalo_mock.html")
        await page.goto(file_path)
        
        # Read the js_scraper from backend/automation.py
        with open("backend/automation.py", "r", encoding="utf-8") as f:
            content = f.read()
            import re
            
            # Extract JS_ASSOCIATE_MEDIA
            m_js = re.search(r'JS_ASSOCIATE_MEDIA = r"""(.*?)"""', content, re.DOTALL)
            js_associate = m_js.group(1) if m_js else ""
            
            # Extract js_scraper body
            m = re.search(r'js_scraper = JS_ASSOCIATE_MEDIA \+ r"""\n        \(args\) => \{(.*?)\n        \}\n        """', content, re.DOTALL)
            if not m:
                m = re.search(r'js_scraper = r"""\n        \(args\) => \{(.*?)\n        \}\n        """', content, re.DOTALL)
                
            if not m:
                print("Could not find js_scraper")
                return
            
            js_code = js_associate + "\n(args) => {" + m.group(1) + "\n}"
            
        result = await page.evaluate(js_code, {"direction": "down"})
        
        print(json.dumps(result["packages"], indent=2, ensure_ascii=False))
        
        await browser.close()

asyncio.run(run_test())
