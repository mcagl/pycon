# Generated by Django 3.2.12 on 2023-01-19 22:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('schedule', '0041_migrate_schedule_items_to_talk_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='scheduleitem',
            name='type',
            field=models.CharField(choices=[('submission', 'Submission'), ('talk', 'Talk'), ('training', 'Training'), ('keynote', 'Keynote'), ('panel', 'Panel'), ('custom', 'Custom')], max_length=10, verbose_name='type'),
        ),
    ]
