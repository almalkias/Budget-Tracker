from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0007_transaction_cycle'),
    ]

    operations = [
        migrations.CreateModel(
            name='MerchantMemory',
            fields=[
                ('id',         models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('merchant',   models.CharField(max_length=200, unique=True)),
                ('category',   models.CharField(max_length=50)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name':        'ذاكرة التاجر',
                'verbose_name_plural': 'ذاكرة التجار',
            },
        ),
    ]
