# Generated by Django 3.2.12 on 2023-01-12 10:55

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('conferences', '0029_store_selected_bed_layout'),
        ('job_board', '0004_change_job_url_to_textfield'),
    ]

    operations = [
        migrations.AddField(
            model_name='joblisting',
            name='conference',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='job_listings', to='conferences.conference', verbose_name='conference'),
        ),
    ]
