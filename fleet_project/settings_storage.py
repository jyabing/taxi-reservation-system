# fleet_project/settings_storage.py
import os
from django.core.exceptions import ImproperlyConfigured

# 默认使用 django-storages 的 S3 后端（兼容 Cloudflare R2）
DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

# 读取环境变量
AWS_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")

if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME, R2_ACCOUNT_ID]):
    raise ImproperlyConfigured("❌ Missing one or more R2 environment variables")

# R2 endpoint
AWS_S3_ENDPOINT_URL = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

# 关键参数
AWS_S3_REGION_NAME = "auto"
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_ADDRESSING_STYLE = "path"   # ⚠️ R2 必须 path 模式

# 上传策略
AWS_QUERYSTRING_AUTH = False       # URL 不带签名参数
AWS_S3_FILE_OVERWRITE = False      # 同名文件不覆盖
AWS_DEFAULT_ACL = None             # 不要默认 ACL
