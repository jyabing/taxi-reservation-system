from django.db import migrations, models
import django.db.models.deletion

def forwards(apps, schema_editor):
    Driver    = apps.get_model('staffbook', 'Driver')
    Company   = apps.get_model('staffbook', 'Company')
    Workplace = apps.get_model('staffbook', 'Workplace')

    for d in Driver.objects.all().only('id', 'company', 'workplace'):
        comp_name = (d.company or '').strip() or '未設定'
        comp, _ = Company.objects.get_or_create(name=comp_name)

        wp_name = (d.workplace or '').strip() or '未設定'
        wp, _ = Workplace.objects.get_or_create(company=comp, name=wp_name)

        # 写入临时外键
        setattr(d, 'company_fk_id', comp.id)
        setattr(d, 'workplace_fk_id', wp.id)
        d.save(update_fields=['company_fk', 'workplace_fk'])

class Migration(migrations.Migration):
    dependencies = [
        ('staffbook', '0017_driverpayrollrecord_progressive_fee'),
    ]
    operations = [
        migrations.CreateModel(
            name='Company',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Workplace',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='workplaces', to='staffbook.company')),
            ],
            options={'unique_together': {('company', 'name')}},
        ),
        # 给 Driver 临时加两个外键
        migrations.AddField(
            model_name='driver',
            name='company_fk',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='drivers_tmp', to='staffbook.company', verbose_name='事業者名'),
        ),
        migrations.AddField(
            model_name='driver',
            name='workplace_fk',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='drivers_tmp2', to='staffbook.workplace', verbose_name='営業所名'),
        ),
        # 把旧 CharField 数据搬到外键
        migrations.RunPython(forwards, migrations.RunPython.noop),
        # 删除旧列
        migrations.RemoveField(model_name='driver', name='company'),
        migrations.RemoveField(model_name='driver', name='workplace'),
        # 临时外键重命名为正式字段
        migrations.RenameField(model_name='driver', old_name='company_fk',   new_name='company'),
        migrations.RenameField(model_name='driver', old_name='workplace_fk', new_name='workplace'),
    ]
