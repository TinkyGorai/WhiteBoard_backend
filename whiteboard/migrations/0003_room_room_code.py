# Generated by Django 5.0.1 on 2025-06-22 03:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whiteboard', '0002_alter_room_created_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='room',
            name='room_code',
            field=models.CharField(blank=True, max_length=6, null=True, unique=True),
        ),
    ]
