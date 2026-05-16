from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0004_budgetcycle'),
    ]

    operations = [
        migrations.AddField(
            model_name='budgetcycle',
            name='salary',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.RemoveField(
            model_name='budgetcycle',
            name='remaining_balance',
        ),
        migrations.RemoveField(
            model_name='budgetcycle',
            name='starting_balance',
        ),
    ]
