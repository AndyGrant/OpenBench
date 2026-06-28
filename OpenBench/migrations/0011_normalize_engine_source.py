# Normalize every Engine.source into the modern GitHub API zipball form:
#
#     https://api.github.com/repos/<owner>/<repo>/zipball/<sha>
#
# Historically the source has been stored in three different shapes. Once they
# all share the modern shape, downstream code (e.g. gitDiffLink) can rely on a
# single, predictable layout.

from django.db import migrations


def normalize_engine_source(apps, schema_editor):

    Engine = apps.get_model('OpenBench', 'Engine')

    for engine in Engine.objects.all():

        source = engine.source
        parts  = source.split('/')

        # Path 1 -- legacy GitHub archive download, of the form
        #   https://github.com/<owner>/<repo>/archive/<sha>.zip
        # The owner and repo are simply the two segments after the host.
        if '/archive/' in source:
            owner, repo = parts[3], parts[4]

        # Path 2 -- legacy GitHub Actions artifacts URL, of the form
        #   https://api.github.com/repos/<owner>/<repo>/actions/runs/<id>/artifacts
        # The owner and repo are the two segments that follow "repos".
        elif '/actions/' in source:
            index       = parts.index('repos')
            owner, repo = parts[index + 1], parts[index + 2]

        # Anything else is already the modern zipball form; leave it untouched.
        else:
            continue

        # Both legacy shapes rebuild to the modern zipball URL, using the
        # engine's recorded commit sha as the canonical reference.
        engine.source = 'https://api.github.com/repos/%s/%s/zipball/%s' % (owner, repo, engine.sha)
        engine.save(update_fields=['source'])


class Migration(migrations.Migration):

    dependencies = [
        ('OpenBench', '0010_remove_test_awaiting'),
    ]

    operations = [
        migrations.RunPython(normalize_engine_source, migrations.RunPython.noop),
    ]
