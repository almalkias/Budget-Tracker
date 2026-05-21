from django.db import migrations, models


INITIAL_CATEGORIES = [
    ('supermarket', 'سوبر ماركت',   10),
    ('food',        'مطاعم وتوصيل', 20),
    ('car',         'السيارة',       30),
    ('clothes',     'ملابس وخياط',  40),
    ('pharmacy',    'صيدلية',        50),
    ('cash',        'سحب كاش',       60),
    ('family',      'تحويل للعائلة', 70),
    ('bnpl',        'تابي وتمارا',   80),
    ('visa',        'تسديد الفيزا',  90),
    ('maids',       'شغالات',       100),
    ('school',      'طلبات مدرسة',  110),
    ('laundry',     'مغسلة ملابس',  120),
    ('maintenance', 'صيانة البيت',  130),
    ('reserve_in',  'تحويل الى الاحتياطي', 140),
    ('reserve_out', 'تحويل من الاحتياطي',  150),
]


def populate_categories(apps, schema_editor):
    Category = apps.get_model('tracker', 'Category')
    existing_keys = set(Category.objects.values_list('key', flat=True))

    for key, label, order in INITIAL_CATEGORIES:
        if key not in existing_keys:
            Category.objects.create(key=key, label=label, order=order)

    # Migrate any custom categories that were saved previously
    try:
        CustomCategory = apps.get_model('tracker', 'CustomCategory')
        for cc in CustomCategory.objects.all():
            if cc.key not in existing_keys and cc.key not in {k for k, _, _ in INITIAL_CATEGORIES}:
                Category.objects.get_or_create(key=cc.key, defaults={'label': cc.key, 'order': 999})
    except Exception:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0012_custom_category'),
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id',    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key',   models.CharField(max_length=100, unique=True)),
                ('label', models.CharField(max_length=200)),
                ('order', models.IntegerField(default=999)),
            ],
            options={
                'verbose_name':        'فئة',
                'verbose_name_plural': 'الفئات',
                'ordering':            ['order', 'key'],
            },
        ),
        migrations.RunPython(populate_categories, migrations.RunPython.noop),
        migrations.DeleteModel(name='CustomCategory'),
    ]
