# -*- coding: utf-8 -*-
# Generated by Harry
from __future__ import unicode_literals

from django.db import migrations


def migrate_favs_forward(apps, schema_editor):
    profile = apps.get_model('aristotle_mdr', 'PossumProfile')

    tag = apps.get_model('aristotle_mdr_favourites', 'Tag')
    favourite = apps.get_model('aristotle_mdr_favourites', 'Favourite')

    for prof in profile.objects.all():
        favtag, created = tag.objects.get_or_create(
            profile=prof,
            name='',
            primary=True
        )

        for item in prof.old_favourites.all():
            favourite.objects.create(
                tag=favtag,
                item=item
            )


def migrate_favs_backward(apps, schema_editor):
    print('------ Favourites can not be migrated backwards -----')


class Migration(migrations.Migration):

    dependencies = [
        ('aristotle_mdr', '0040_rename_favourites'),
        ('aristotle_mdr_favourites', '0004_auto_20180913_2021')
    ]

    operations = [
        migrations.RunPython(migrate_favs_forward, migrate_favs_backward)
    ]