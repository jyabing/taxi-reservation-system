from django.db import migrations, models
import django.db.models.deletion

def forwards(apps, schema_editor):
    Driver    = apps.get_model('staffbook', 'Driver')
    Company   = apps.get_model('staffbook', 'Company')
    Workplace = apps.get_model('staffbook', 'Workplace')

    default_c, _ = Company.objects.get_or_create(name="光交通株式会社")
    default_w, _ = Workplace.objects.get_or_create(company=default_c, name="京都営業所")

    for d in Driver.objects.all():
        cname = (getattr(d, 'company', '') or '').strip() or default_c.name
        wname = (getattr(d, 'workplace', '') or '').strip() or default_w.name
        cobj, _ = Company.objects.get_or_create(name=cname)
        wobj, _ = Workplace.objects.get_or_create(company=cobj, name=wname)
        d.company_fk_id = cobj.id
        d.workplace_fk_id = wobj.id
        d.save(update_fields=['company_fk', 'workplace_fk'])

def backwards(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('staffbook', '0017_driverpayrollrecord_progressive_fee'),
    ]
    operations = [
        migrations.CreateModel(
            name='Company',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Workplace',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='workplaces', to='staffbook.company')),
            ],
            options={'unique_together': {('company', 'name')}},
        ),
        migrations.AddField(
            model_name='driver',
            name='alt_name',
            field=models.CharField(verbose_name='別名', max_length=32, blank=True, default=''),
        ),
        migrations.AddField(
            model_name='driver',
            name='alt_kana',
            field=models.CharField(verbose_name='別名フリガナ', max_length=32, blank=True, default=''),
        ),
        migrations.AddField(
            model_name='driver',
            name='company_fk',
            field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='staffbook.company'),
        ),
        migrations.AddField(
            model_name='driver',
            name='workplace_fk',
            field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='staffbook.workplace'),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(model_name='driver', name='company'),
        migrations.RemoveField(model_name='driver', name='workplace'),
        migrations.RenameField(model_name='driver', old_name='company_fk', new_name='company'),
        migrations.RenameField(model_name='driver', old_name='workplace_fk', new_name='workplace'),
        migrations.AlterField(
            model_name='driver',
            name='company',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='drivers', to='staffbook.company', verbose_name='事業者名'),
        ),
        migrations.AlterField(
            model_name='driver',
            name='workplace',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='drivers', to='staffbook.workplace', verbose_name='営業所名'),
        ),
    ]
