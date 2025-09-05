import os
from django.core.exceptions import ImproperlyConfigured

DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

# 必填：这四个缺一不可
AWS_ACCESS_KEY_ID       = os.getenv("R2_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY   = os.getenv("R2_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_ACCOUNT_ID           = os.getenv("R2_ACCOUNT_ID")

_missing = [k for k, v in {
    "R2_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
    "R2_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
    "R2_BUCKET_NAME": AWS_STORAGE_BUCKET_NAME,
    "R2_ACCOUNT_ID": R2_ACCOUNT_ID,
}.items() if not v]
if _missing:
    raise ImproperlyConfigured("Missing env var(s): " + ", ".join(_missing))

# ✅ 公共直链域名：可选。优先取 env；没有则按账号 ID 推导
R2_PUBLIC_DOMAIN = (
    os.getenv("R2_PUBLIC_DOMAIN") or
    os.getenv("AWS_S3_CUSTOM_DOMAIN") or
    f"pub-{R2_ACCOUNT_ID}.r2.dev"
)

# 后端上传/签名用（S3 API 端点）—— 只能用 cloudflarestorage.com
AWS_S3_ENDPOINT_URL      = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
# 前端展示用（直链域名，不参与签名）
AWS_S3_CUSTOM_DOMAIN     = R2_PUBLIC_DOMAIN
AWS_S3_URL_PROTOCOL      = "https:"

# R2 必需参数
AWS_S3_REGION_NAME       = "auto"
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_ADDRESSING_STYLE  = "virtual"

# 上传/URL 策略
AWS_QUERYSTRING_AUTH     = False
AWS_S3_FILE_OVERWRITE    = True   # 用 uuid 文件名即可，不检查 exists
AWS_DEFAULT_ACL          = None
