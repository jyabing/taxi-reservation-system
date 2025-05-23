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

def upload_image(file_path, folder="vehicles"):
    try:
        file_name = os.path.basename(file_path)
        public_id = os.path.splitext(file_name)[0]
        result = cloudinary.uploader.upload(
            file_path,
            folder=folder,
            public_id=public_id,
            overwrite=True,
        )
        print("✅ 上传成功")
        print("图片名称：", result.get("original_filename"))
        print("图片 URL：", result.get("secure_url"))
        return result.get("secure_url")
    except Exception as e:
        print("❌ 上传失败：", str(e))
        return None

if __name__ == "__main__":
    file_path = input("请输入图片路径（如 media/carousel/xxx.jpg）：")
    upload_image(file_path)