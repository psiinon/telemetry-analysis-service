# -*- coding: utf-8 -*-
# Generated by Django 1.11.1 on 2017-05-17 13:39
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0026_sparkjobrun_size'),
    ]

    operations = [
        migrations.RenameField(
            model_name='sparkjobrun',
            old_name='terminated_date',
            new_name='finished_at',
        ),
    ]
