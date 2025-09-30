# staffbook/migrations/0005_drop_legacy_company_fk.py
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('staffbook', '0004_driver_company_driver_workplace'),
    ]

    operations = [
        # 确保 CharField 列存在（若已存在则跳过）
        migrations.RunSQL(
            sql=(
                "ALTER TABLE staffbook_driver "
                "ADD COLUMN IF NOT EXISTS company varchar(64) DEFAULT '' NOT NULL;"
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE staffbook_driver "
                "ADD COLUMN IF NOT EXISTS workplace varchar(64) DEFAULT '' NOT NULL;"
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),

        # 删除遗留的 FK 列（若不存在则跳过）
        migrations.RunSQL(
            sql="ALTER TABLE staffbook_driver DROP COLUMN IF EXISTS company_id CASCADE;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="ALTER TABLE staffbook_driver DROP COLUMN IF EXISTS workplace_id CASCADE;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
