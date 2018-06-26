# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-06-21 02:17
from __future__ import unicode_literals

from django.db import migrations, models
import aristotle_mdr.fields

class Migration(migrations.Migration):

    dependencies = [
        ('aristotle_mdr', '0029_remove__concept_short_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='possumprofile',
            name='profilePicture',
            field=aristotle_mdr.fields.ConvertedConstrainedImageField(blank=True, height_field='profilePictureHeight', js_checker=True, max_upload_size=1073741824, mime_lookup_length=4096, null=True, upload_to='', width_field='profilePictureWidth'),
        ),
        migrations.AddField(
            model_name='possumprofile',
            name='profilePictureHeight',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='possumprofile',
            name='profilePictureWidth',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
