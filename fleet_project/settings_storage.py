# fleet_project/settings_storage.py
import os
from django.core.exceptions import ImproperlyConfigured

# 用 django-storages 的 S3 后端（兼容 R2）
DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

# 必要环境变量
AWS_ACCESS_KEY_ID        = os.getenv("R2_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY    = os.getenv("R2_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME  = os.getenv("R2_BUCKET_NAME")
R2_ACCOUNT_ID            = os.getenv("R2_ACCOUNT_ID")

if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME, R2_ACCOUNT_ID]):
    raise ImproperlyConfigured("❌ Missing one or more R2 environment variables")

# boto3 连接用的 API Endpoint（走 s3 协议）
AWS_S3_ENDPOINT_URL = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

# 生成前端可访问的 URL 用的公共域（无签名、可直链）
# 若你愿意用 env 配置，也可以用 os.getenv("AWS_S3_CUSTOM_DOMAIN") 覆盖
AWS_S3_CUSTOM_DOMAIN = f"pub-{R2_ACCOUNT_ID}.r2.dev"
AWS_S3_URL_PROTOCOL  = "https:"   # 明确协议，避免相对协议

# R2 关键参数
AWS_S3_REGION_NAME        = "auto"
AWS_S3_SIGNATURE_VERSION  = "s3v4"
AWS_S3_ADDRESSING_STYLE   = "path"   # R2 必须 path

# 上传/URL 策略
AWS_QUERYSTRING_AUTH  = False        # 生成的 URL 不带 ?X-Amz-*
AWS_S3_FILE_OVERWRITE = False        # 同名不覆盖
AWS_DEFAULT_ACL       = None         # 不使用默认 ACL
