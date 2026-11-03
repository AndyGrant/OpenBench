# Add Network.ob_compressed, and build a zstd compressed copy of every Network
# file already on disk, stored alongside the original as Media/<sha256>.zst
#
# Networks whose name already ends in a compression suffix are skipped, since
# compressing them again would be redundant.

import os

from django.conf import settings
from django.core.management.base import CommandError
from django.db import migrations, models

COMPRESSED_SUFFIXES = (
    '.zst', '.zstd', '.gz', '.gzip', '.bz2', '.xz', '.lzma', '.zip', '.7z', '.lz4', '.br', '.z',
)


def compress_networks(apps, schema_editor):

    # Imported here, so a missing package fails with a clear message. The whole
    # migration rolls back, and can be re-run once the package is installed
    try:
        import zstandard
    except ImportError:
        raise CommandError(
            'The zstandard package is not installed, but is required by this migration. '
            'Please run: pip3 install -r requirements.txt   then re-run the migration.')

    Network = apps.get_model('OpenBench', 'Network')

    for sha256 in Network.objects.values_list('sha256', flat=True).distinct():

        source = os.path.join(settings.MEDIA_ROOT, sha256)
        target = source + '.zst'

        # Several Networks may share one file; skip it if any of them are
        # named as compressed, since the stored file is then compressed already
        names = Network.objects.filter(sha256=sha256).values_list('name', flat=True)
        if any(name.lower().endswith(COMPRESSED_SUFFIXES) for name in names):
            continue

        if not os.path.isfile(source):
            continue

        # Write to a temp file first, so a partial copy is never left behind
        if not os.path.isfile(target):
            with open(source, 'rb') as fin, open(target + '.tmp', 'wb') as fout:
                zstandard.ZstdCompressor().copy_stream(fin, fout)
            os.replace(target + '.tmp', target)

        Network.objects.filter(sha256=sha256).update(ob_compressed=True)


class Migration(migrations.Migration):

    dependencies = [
        ('OpenBench', '0016_engineconfig_serverstate'),
    ]

    operations = [
        migrations.AddField(
            model_name='network',
            name='ob_compressed',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(compress_networks, migrations.RunPython.noop),
    ]
