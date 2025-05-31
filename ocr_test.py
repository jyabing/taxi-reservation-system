import pytesseract
from PIL import Image
import cv2
import numpy as np

# 设置语言路径（一般系统会自动识别）
# pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

# 载入图片
image_path = 'media/report_images/IMG_1365.JPEG'  # 改成你的路径
img = cv2.imread(image_path)

# 灰度处理 + 二值化 + 降噪（你可以多试试）
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
_, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

# OCR识别
text = pytesseract.image_to_string(thresh, lang='jpn')  # 或 lang='jpn+eng'

# 打印识别内容
print("🧠 识别结果：\n")
print(text)
