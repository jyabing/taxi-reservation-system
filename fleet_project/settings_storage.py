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
# ⚠️ 这里必须是 Cloudflare 分配的真实 r2.dev 域名，比如：
# pub-48d6e7c8197d4dde7a3f41f343085e209.r2.dev
AWS_S3_CUSTOM_DOMAIN     = os.getenv("R2_PUBLIC_DOMAIN") or os.getenv("AWS_S3_CUSTOM_DOMAIN")

_missing = [k for k, v in {
    "R2_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
    "R2_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
    "R2_BUCKET_NAME": AWS_STORAGE_BUCKET_NAME,
    "R2_ACCOUNT_ID": R2_ACCOUNT_ID,
    "R2_PUBLIC_DOMAIN/AWS_S3_CUSTOM_DOMAIN": AWS_S3_CUSTOM_DOMAIN,
}.items() if not v]
if _missing:
    raise ImproperlyConfigured("Missing env var(s): " + ", ".join(_missing))

# boto3 用的 S3 API 端点
AWS_S3_ENDPOINT_URL = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

# 前端直链用 r2.dev 域名
AWS_S3_URL_PROTOCOL  = "https:"   # 明确协议
AWS_S3_REGION_NAME        = "auto"
AWS_S3_SIGNATURE_VERSION  = "s3v4"
AWS_S3_ADDRESSING_STYLE   = "path"   # R2 用 path
AWS_QUERYSTRING_AUTH      = False
AWS_S3_FILE_OVERWRITE     = True
AWS_DEFAULT_ACL           = None
