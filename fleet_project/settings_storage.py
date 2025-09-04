# fleet_project/settings_storage.py
import os
from django.core.exceptions import ImproperlyConfigured

# ===== 可见性标记，便于确认这个文件真的被加载 =====
R2_MARKER = "settings_storage_loaded"

# 用 django-storages 的 S3 后端连 R2
DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

# --- 凭据（优先 R2_*，否则 AWS_*) ---
AWS_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = os.getenv("R2_BUCKET_NAME") or os.getenv("AWS_STORAGE_BUCKET_NAME") or "fleet-media"

# --- R2 S3 端点 ---
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID") or "29c4dd28d4cf9b19c63d3da64fd32d0a"
AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL") or f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

AWS_S3_REGION_NAME = "auto"
AWS_S3_SIGNATURE_VERSION = "s3v4"

# ========== 关键：使用 r2.dev 公网域，生成无签名直链 ==========
AWS_S3_CUSTOM_DOMAIN = "pub-48d6e7c8197d4dde7a3f41f343085e209.r2.dev"   # ← 换成你自己的域名
AWS_S3_ADDRESSING_STYLE = "path"        # 必须 path： https://pub.../bucket/key
AWS_QUERYSTRING_AUTH = False            # 不要带 ?X-Amz-Signature
# ===========================================================

AWS_S3_FILE_OVERWRITE = False
AWS_DEFAULT_ACL = None
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "public, max-age=31536000"}

# 关键环境缺失时的提示（端点可由 ACCOUNT_ID 推出，这里不强制）
_missing = [k for k, v in {
    "AWS_ACCESS_KEY_ID/R2_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
    "AWS_SECRET_ACCESS_KEY/R2_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
    "AWS_STORAGE_BUCKET_NAME/R2_BUCKET_NAME": AWS_STORAGE_BUCKET_NAME,
}.items() if not v]
if _missing:
    raise ImproperlyConfigured(f"Missing env vars for R2: {', '.join(_missing)}")
