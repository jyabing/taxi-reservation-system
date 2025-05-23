import os
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

def upload_image(file_path):
    result = cloudinary.uploader.upload(file_path)
    print("✅ 上传成功")
    print("图片名称：", result.get("original_filename"))
    print("图片 URL：", result.get("secure_url"))

if __name__ == "__main__":
    upload_image("media/carousel/IMG_1046.JPEG")  # ← 请替换为你本地路径