import os
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
import boto3
from botocore.config import Config


class Command(BaseCommand):
    help = "Check Cloudflare R2 connectivity and basic read/write via boto3 + Django storage"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Clean up test objects after check",
        )

    def handle(self, *args, **options):
        bucket = os.getenv("R2_BUCKET_NAME")
        account_id = os.getenv("R2_ACCOUNT_ID")
        ak = os.getenv("R2_ACCESS_KEY_ID")
        sk = os.getenv("R2_SECRET_ACCESS_KEY")

        if not all([bucket, account_id, ak, sk]):
            self.stderr.write(self.style.ERROR("❌ Missing R2 environment variables"))
            return

        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"

        # ✅ 用 virtual（或直接去掉 s3=... 这一项）
        cfg = Config(signature_version="s3v4", s3={"addressing_style": "virtual"})

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=ak,
            aws_secret_access_key=sk,
            region_name="auto",
            config=cfg,
        )

        key_boto3 = "health/r2check.txt"
        key_django = "health/django_r2check.txt"

        try:
            # 1. bucket 可用性
            self.stdout.write("1️⃣ head_bucket ...")
            s3.head_bucket(Bucket=bucket)
            self.stdout.write(self.style.SUCCESS("✅ bucket exists and accessible"))

            # 2. boto3 上传
            self.stdout.write("2️⃣ put_object ...")
            s3.put_object(Bucket=bucket, Key=key_boto3, Body=b"hello-r2check")
            self.stdout.write(self.style.SUCCESS(f"✅ object uploaded: {key_boto3}"))

            # 3. boto3 下载
            self.stdout.write("3️⃣ get_object ...")
            obj = s3.get_object(Bucket=bucket, Key=key_boto3)
            body = obj["Body"].read()
            self.stdout.write(self.style.SUCCESS(f"✅ object fetched, content={body!r}"))

            # 4. Django 存储测试
            self.stdout.write("4️⃣ Django default_storage test ...")
            default_storage.save(key_django, ContentFile(b"django-r2check"))
            if default_storage.exists(key_django):
                url = default_storage.url(key_django)
                self.stdout.write(self.style.SUCCESS(f"✅ Django storage works, url={url}"))
            else:
                self.stderr.write(self.style.ERROR("❌ Django storage save failed"))

            # 5. 清理（如果传了 --clean）
            if options["clean"]:
                self.stdout.write("🧹 cleaning up test objects ...")
                s3.delete_object(Bucket=bucket, Key=key_boto3)
                if default_storage.exists(key_django):
                    default_storage.delete(key_django)
                self.stdout.write(self.style.SUCCESS("✅ cleaned up test objects"))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"❌ Error: {e}"))
