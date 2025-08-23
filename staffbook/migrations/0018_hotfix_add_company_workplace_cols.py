from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('staffbook', '0017_driverpayrollrecord_progressive_fee'),
    ]

    operations = [
        migrations.RunSQL(
            """
            ALTER TABLE staffbook_driver
            ADD COLUMN IF NOT EXISTS company   varchar(64);
            """,
            reverse_sql="""
            -- 保守起见，不自动删
            """
        ),
        migrations.RunSQL(
            """
            ALTER TABLE staffbook_driver
            ADD COLUMN IF NOT EXISTS workplace varchar(64);
            """,
            reverse_sql="""
            -- 保守起见，不自动删
            """
        ),
        migrations.RunSQL(
            """
            UPDATE staffbook_driver SET company=''   WHERE company   IS NULL;
            UPDATE staffbook_driver SET workplace='' WHERE workplace IS NULL;
            """,
            reverse_sql="""
            -- no-op
            """
        ),
    ]
