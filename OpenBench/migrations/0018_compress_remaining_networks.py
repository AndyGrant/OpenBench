# Build a zstd compressed copy of every Network file that does not have one yet,
# such as those uploaded after migration 0017, and flag the Networks as compressed.
#
# Networks whose name already ends in a compression suffix are skipped.

import os
import zstandard

from django.conf import settings
from django.db import migrations

COMPRESSED_SUFFIXES = (
    '.zst', '.zstd', '.gz', '.gzip', '.bz2', '.xz', '.lzma', '.zip', '.7z', '.lz4', '.br', '.z',
)


def compress_networks(apps, schema_editor):

    Network = apps.get_model('OpenBench', 'Network')

    for sha256 in Network.objects.values_list('sha256', flat=True).distinct():

        source = os.path.join(settings.MEDIA_ROOT, sha256)
        target = source + '.zst'

        names = Network.objects.filter(sha256=sha256).values_list('name', flat=True)
        if any(name.lower().endswith(COMPRESSED_SUFFIXES) for name in names):
            continue

        if not os.path.isfile(source):
            continue

        if not os.path.isfile(target):
            with open(source, 'rb') as fin, open(target + '.tmp', 'wb') as fout:
                zstandard.ZstdCompressor().copy_stream(fin, fout)
            os.replace(target + '.tmp', target)

        # Also repairs rows flagged False despite the file existing
        Network.objects.filter(sha256=sha256, ob_compressed=False).update(ob_compressed=True)


class Migration(migrations.Migration):

    dependencies = [
        ('OpenBench', '0017_network_ob_compressed'),
    ]

    operations = [
        migrations.RunPython(compress_networks, migrations.RunPython.noop),
    ]
