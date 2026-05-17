from django.db import migrations, models
import django.db.models.deletion


def backfill_cycles(apps, schema_editor):
    Transaction = apps.get_model('tracker', 'Transaction')
    BudgetCycle = apps.get_model('tracker', 'BudgetCycle')

    cycles = list(BudgetCycle.objects.order_by('started_at'))
    if not cycles:
        return

    for tx in Transaction.objects.filter(is_categorized=True):
        assigned = None
        for cycle in cycles:
            if cycle.status == 'active':
                if tx.created_at >= cycle.started_at:
                    assigned = cycle
            else:
                end = cycle.closed_at or cycle.started_at
                if cycle.started_at <= tx.created_at <= end:
                    assigned = cycle
                    break
        tx.cycle = assigned
        tx.save(update_fields=['cycle'])


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0006_remove_merchantrule_transaction_is_skipped'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='cycle',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='transactions',
                to='tracker.budgetcycle',
            ),
        ),
        migrations.RunPython(backfill_cycles, migrations.RunPython.noop),
    ]
