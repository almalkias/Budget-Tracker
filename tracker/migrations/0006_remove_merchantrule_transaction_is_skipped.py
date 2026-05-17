from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0005_budgetcycle_salary'),
    ]

    operations = [
        migrations.DeleteModel(
            name='MerchantRule',
        ),
        migrations.AddField(
            model_name='transaction',
            name='is_skipped',
            field=models.BooleanField(default=False),
        ),
    ]
