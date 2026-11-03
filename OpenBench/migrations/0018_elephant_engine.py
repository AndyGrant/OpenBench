# Upstream moved engines out of Config/config.json and Engines/*.json into the database (0016, EngineConfig).
# The lab's one engine, Elephant, is created here from Engines/elephant.json, where it was before, so a server
# that migrates still offers it. An Elephant already in the database (edited on the website) is left alone.
# The books are upstream's (0015); every book this lab listed is among them.

import json
import os

from django.conf import settings
from django.db import migrations


def create_elephant(apps, schema_editor):

    EngineConfig = apps.get_model('OpenBench', 'EngineConfig')
    path = os.path.join(settings.PROJECT_PATH, 'Engines', 'elephant.json')

    if EngineConfig.objects.filter(name='elephant').exists() or not os.path.isfile(path):
        return

    from OpenBench.management.commands.import_engines import engine_fields

    with open(path) as fin:
        conf = json.load(fin)

    EngineConfig.objects.create(name='elephant', **engine_fields(path, 'elephant', conf))


class Migration(migrations.Migration):

    dependencies = [
        ('OpenBench', '0017_network_ob_compressed'),
    ]

    operations = [
        migrations.RunPython(create_elephant, migrations.RunPython.noop),
    ]
