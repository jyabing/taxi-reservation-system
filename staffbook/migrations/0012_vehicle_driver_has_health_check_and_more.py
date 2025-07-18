# Generated by Django 5.1.2 on 2025-07-03 21:56

import datetime
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('carinfo', '0005_car_body_shape_car_car_type_code_car_engine_model_and_more'),
        ('staffbook', '0011_driverdailyreportitem_is_flagged'),
    ]

    operations = [
        migrations.CreateModel(
            name='Vehicle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, verbose_name='车辆名')),
                ('plate_number', models.CharField(max_length=20, verbose_name='车牌号')),
            ],
        ),
        migrations.AddField(
            model_name='driver',
            name='has_health_check',
            field=models.BooleanField(default=False, verbose_name='健康診断書提出済'),
        ),
        migrations.AddField(
            model_name='driver',
            name='has_license_copy',
            field=models.BooleanField(default=False, verbose_name='免許証コピー提出済'),
        ),
        migrations.AddField(
            model_name='driver',
            name='has_residence_certificate',
            field=models.BooleanField(default=False, verbose_name='住民票提出済'),
        ),
        migrations.AddField(
            model_name='driver',
            name='has_tax_form',
            field=models.BooleanField(default=False, verbose_name='扶養控除等申告書提出済'),
        ),
        migrations.AddField(
            model_name='driver',
            name='is_foreign',
            field=models.BooleanField(default=False, verbose_name='外国籍'),
        ),
        migrations.AddField(
            model_name='driver',
            name='nationality',
            field=models.CharField(blank=True, max_length=32, null=True, verbose_name='国籍'),
        ),
        migrations.AddField(
            model_name='driver',
            name='residence_card_image',
            field=models.ImageField(blank=True, null=True, upload_to='residence_cards/', verbose_name='在留カード画像'),
        ),
        migrations.AddField(
            model_name='driver',
            name='residence_expiry',
            field=models.DateField(blank=True, null=True, verbose_name='在留期限'),
        ),
        migrations.AddField(
            model_name='driver',
            name='residence_status',
            field=models.CharField(blank=True, choices=[('日本人の配偶者等', '日本人の配偶者等'), ('永住者', '永住者'), ('定住者', '定住者'), ('家族滞在', '家族滞在'), ('技術・人文知識・国際業務', '技術・人文知識・国際業務'), ('技能', '技能'), ('技能実習', '技能実習'), ('特定技能46号', '特定技能46号'), ('留学', '留学'), ('研修', '研修'), ('短期滞在', '短期滞在'), ('その他', 'その他')], max_length=64, null=True, verbose_name='在留資格'),
        ),
        migrations.AddField(
            model_name='driver',
            name='resigned_date',
            field=models.DateField(blank=True, null=True, verbose_name='退職日'),
        ),
        migrations.AddField(
            model_name='driver',
            name='work_permission_confirmed',
            field=models.BooleanField(default=False, verbose_name='就労資格確認済'),
        ),
        migrations.AddField(
            model_name='driverdailyreport',
            name='deposit_amount',
            field=models.PositiveIntegerField(blank=True, help_text='手动输入的入金金额', null=True, verbose_name='入金額'),
        ),
        migrations.AddField(
            model_name='driverdailyreport',
            name='deposit_difference',
            field=models.IntegerField(blank=True, help_text='入金 − 現金', null=True, verbose_name='過不足額'),
        ),
        migrations.AddField(
            model_name='driverdailyreport',
            name='vehicle',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='daily_reports', to='carinfo.car', verbose_name='本日使用车辆'),
        ),
        migrations.AddField(
            model_name='driverdailyreport',
            name='休憩時間',
            field=models.DurationField(blank=True, default=datetime.timedelta(seconds=1200), null=True, verbose_name='休憩時間'),
        ),
        migrations.AddField(
            model_name='driverdailyreport',
            name='勤務時間',
            field=models.DurationField(blank=True, null=True, verbose_name='勤務時間'),
        ),
        migrations.AddField(
            model_name='driverdailyreport',
            name='実働時間',
            field=models.DurationField(blank=True, null=True, verbose_name='実働時間'),
        ),
        migrations.AddField(
            model_name='driverdailyreport',
            name='残業時間',
            field=models.DurationField(blank=True, null=True, verbose_name='残業時間'),
        ),
        migrations.AlterField(
            model_name='driver',
            name='employ_type',
            field=models.CharField(choices=[('1', '正式運転者'), ('2', '非常勤運転者'), ('3', '退職者')], max_length=20, verbose_name='在職類型'),
        ),
        migrations.AlterField(
            model_name='driverdailyreportitem',
            name='is_flagged',
            field=models.BooleanField(default=False, verbose_name='标记为重点'),
        ),
        migrations.AlterField(
            model_name='driverdailyreportitem',
            name='num_female',
            field=models.IntegerField(blank=True, null=True, verbose_name='女性'),
        ),
        migrations.AlterField(
            model_name='driverdailyreportitem',
            name='num_male',
            field=models.IntegerField(blank=True, null=True, verbose_name='男性'),
        ),
        migrations.AlterField(
            model_name='driverdailyreportitem',
            name='payment_method',
            field=models.CharField(blank=True, choices=[('cash', '現金'), ('uber', 'Uber'), ('didi', 'Didi'), ('credit', 'クレジットカード'), ('kyokushin', '京交信'), ('omron', 'オムロン'), ('kyotoshi', '京都市他'), ('qr', '扫码(PayPay/AuPay/支付宝/微信Pay等)')], max_length=16, verbose_name='支付方式'),
        ),
    ]
