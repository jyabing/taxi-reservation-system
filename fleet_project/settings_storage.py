# fleet_project/settings_storage.py
import os
from django.core.exceptions import ImproperlyConfigured

DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

# 兼容读取：优先 R2_*，否则 AWS_*
AWS_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = os.getenv("R2_BUCKET_NAME") or os.getenv("AWS_STORAGE_BUCKET_NAME")

# endpoint：可直接写 AWS_S3_ENDPOINT_URL；否则用 R2_ACCOUNT_ID 自动拼
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
AWS_S3_ENDPOINT_URL = (
    os.getenv("AWS_S3_ENDPOINT_URL")
    or (f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else None)
)

AWS_S3_REGION_NAME = "auto"
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_ADDRESSING_STYLE = "virtual"
AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False
AWS_QUERYSTRING_AUTH = True
AWS_QUERYSTRING_EXPIRE = int(os.getenv("AWS_QUERYSTRING_EXPIRE", "3600"))

# 缺失关键变量时直接提示
_missing = [k for k, v in {
    "AWS_ACCESS_KEY_ID/R2_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
    "AWS_SECRET_ACCESS_KEY/R2_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
    "AWS_STORAGE_BUCKET_NAME/R2_BUCKET_NAME": AWS_STORAGE_BUCKET_NAME,
    "AWS_S3_ENDPOINT_URL or R2_ACCOUNT_ID": AWS_S3_ENDPOINT_URL,
}.items() if not v]
if _missing:
    raise ImproperlyConfigured(f"Missing env vars for R2: {', '.join(_missing)}")
