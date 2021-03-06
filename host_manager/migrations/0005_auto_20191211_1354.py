# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-12-11 13:54
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('host_manager', '0004_hostsnapshot'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='hostsnapshot',
            options={'ordering': ['-create_time']},
        ),
        migrations.AddField(
            model_name='hostsnapshot',
            name='last_task_id',
            field=models.CharField(max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='hostsnapshot',
            name='last_task_name',
            field=models.CharField(max_length=100, null=True),
        ),
    ]
