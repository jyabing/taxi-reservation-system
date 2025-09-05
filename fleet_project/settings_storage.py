import os
from django.core.exceptions import ImproperlyConfigured

DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

AWS_ACCESS_KEY_ID       = os.getenv("R2_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY   = os.getenv("R2_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_ACCOUNT_ID           = os.getenv("R2_ACCOUNT_ID")

for k, v in {
    "R2_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
    "R2_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
    "R2_BUCKET_NAME": AWS_STORAGE_BUCKET_NAME,
    "R2_ACCOUNT_ID": R2_ACCOUNT_ID,
}.items():
    if not v:
        raise ImproperlyConfigured(f"Missing {k}")

AWS_S3_ENDPOINT_URL       = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
AWS_S3_REGION_NAME        = "auto"
AWS_S3_SIGNATURE_VERSION  = "s3v4"
AWS_S3_ADDRESSING_STYLE   = "virtual"

AWS_DEFAULT_ACL        = None
AWS_QUERYSTRING_AUTH   = False
AWS_S3_FILE_OVERWRITE  = True
