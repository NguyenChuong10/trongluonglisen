import os
import cv2
import zxingcpp

data_dir = r"d:\JMS_Helper_Complete_Updated\data\1"

if not os.path.exists(data_dir):
    print("No data directory found")
    exit(1)

for f in os.listdir(data_dir):
    if f.lower().endswith((".jpg", ".jpeg", ".png")):
        img_path = os.path.join(data_dir, f)
        img = cv2.imread(img_path)
        if img is None:
            continue
        print(f"Scanning {f}...")
        results = zxingcpp.read_barcodes(img)
        for res in results:
            print(f"  Found: {res.text} ({res.format})")
        if not results:
            print("  No barcode found")
