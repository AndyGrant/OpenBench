import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import uuid


def import_configuration(apps, schema_editor):
    database = schema_editor.connection.alias
    revision_model = apps.get_model('OpenBench', 'ConfigurationRevision')
    if revision_model.objects.using(database).exists():
        return
    site_model = apps.get_model('OpenBench', 'SiteSettings')
    engine_model = apps.get_model('OpenBench', 'EngineConfig')
    book_model = apps.get_model('OpenBench', 'OpeningBook')
    preset_model = apps.get_model('OpenBench', 'WorkloadPreset')
    if any(model.objects.using(database).exists() for model in (site_model, engine_model, book_model, preset_model)):
        raise RuntimeError('Configuration is partially initialized. Complete import_config --apply before running migrate again.')

    root = Path(settings.BASE_DIR).resolve()

    def read(folder, name):
        path = (root / folder / name).resolve()
        if not path.is_relative_to(root / folder):
            raise ValueError('Configuration path escapes its directory: %s' % path)
        with path.open(encoding='utf-8-sig') as stream:
            value = json.load(stream)
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object in %s' % path)
        return value

    def save(instance):
        instance.full_clean(exclude=[field.name for field in instance._meta.fields if field.is_relation],
            validate_unique=False, validate_constraints=False)
        instance.save(using=database)

    try:
        original = read('Config', 'config.json')
        site = {key: value for key, value in original.items() if key not in ('engines', 'books')}
        snapshot = dict(site, engines={}, books={})
        for section, folder, model in (('engines', 'Engines', engine_model), ('books', 'Books', book_model)):
            names = original[section]
            if not isinstance(names, list) or any(not isinstance(name, str) or not name for name in names):
                raise ValueError('%s must be a list of names.' % section)
            if len(names) != len(set(names)):
                raise ValueError('Duplicate %s names.' % section)
            for name in names:
                data = read(folder, name + '.json')
                presets = []
                if section == 'engines':
                    for field, kind in (('test_presets', 'TEST'), ('tune_presets', 'TUNE'), ('datagen_presets', 'DATAGEN')):
                        entries = data.pop(field, {'default': {}})
                        if not isinstance(entries, dict) or any(not isinstance(values, dict) for values in entries.values()):
                            raise ValueError('Invalid %s for %s.' % (field, name))
                        defaults = entries.get('default', {})
                        resolved = {preset: defaults | values for preset, values in entries.items()}
                        presets.append((field, kind, resolved))
                else:
                    suffix = name.rsplit('.', 1)[-1] if '.' in name else ''
                    if suffix not in ('epd', 'pgn') or data.get('format', suffix) != suffix:
                        raise ValueError('Book %s must have a matching .epd or .pgn extension and format.' % name)
                    data['format'] = suffix
                instance = model(name=name, enabled=True, settings=data)
                save(instance)
                snapshot[section][name] = dict(data)
                for field, kind, entries in presets:
                    snapshot[section][name][field] = {'default': {}, **entries}
                    for position, (preset, values) in enumerate(entries.items()):
                        save(preset_model(engine_id=instance.pk, workload_type=kind, name=preset,
                            settings=values, position=position))
        eligibility = {name: {key: data[key] for key in ('build', 'private', 'source')}
            for name, data in snapshot['engines'].items()}
        worker = {key: value for key, value in site.items() if key.startswith(('client_', 'fastchess_'))}
        checksum = hashlib.sha256(json.dumps([eligibility, worker], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        save(site_model(pk=1, generation=1, settings=site))
        save(revision_model(generation=1, summary='Imported JSON configuration', snapshot=snapshot, checksum=checksum))
    except (OSError, ValueError, TypeError, KeyError, ValidationError) as error:
        raise RuntimeError('Unable to import legacy configuration from %s. Fix the JSON configuration and run migrate again: %s' % (root, error)) from error



class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('OpenBench', '0013_nps_tracking'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfigurationRevision',
            fields=[
                ('generation', models.PositiveBigIntegerField(primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('summary', models.CharField(max_length=256)),
                ('snapshot', models.JSONField()),
                ('checksum', models.CharField(max_length=64)),
                ('actor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-generation'],
            },
        ),
        migrations.CreateModel(
            name='EngineConfig',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=64, unique=True, validators=[django.core.validators.RegexValidator('^[^/\\\\\\x00-\\x1f]+$')])),
                ('enabled', models.BooleanField(default=False)),
                ('settings', models.JSONField(default=dict)),
            ],
            options={
                'ordering': ['name'],
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='OpeningBook',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=32, unique=True, validators=[django.core.validators.RegexValidator('^[^/\\\\\\x00-\\x1f]+$')])),
                ('enabled', models.BooleanField(default=False)),
                ('settings', models.JSONField(default=dict)),
            ],
            options={
                'ordering': ['name'],
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='SiteSettings',
            fields=[
                ('id', models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ('generation', models.PositiveBigIntegerField(default=0)),
                ('settings', models.JSONField(default=dict)),
            ],
            options={
                'constraints': [models.CheckConstraint(check=models.Q(('id', 1)), name='single_site_settings')],
            },
        ),
        migrations.CreateModel(
            name='WorkloadPreset',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=128)),
                ('workload_type', models.CharField(choices=[('TEST', 'Test'), ('TUNE', 'Tune'), ('DATAGEN', 'Datagen')], max_length=8)),
                ('position', models.PositiveIntegerField(default=0)),
                ('settings', models.JSONField(blank=True, default=dict)),
                ('engine', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='presets', to='OpenBench.engineconfig')),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['position', 'name', 'id'],
                'constraints': [models.UniqueConstraint(condition=models.Q(('owner__isnull', True)), fields=('engine', 'workload_type', 'name'), name='unique_shared_preset'), models.UniqueConstraint(condition=models.Q(('owner__isnull', False)), fields=('engine', 'owner', 'workload_type', 'name'), name='unique_personal_preset')],
            },
        ),
        migrations.CreateModel(
            name='EngineMaintainer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('engine', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='maintainers', to='OpenBench.engineconfig')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('engine', 'user'), name='unique_engine_maintainer')],
            },
        ),
        migrations.RunPython(import_configuration, migrations.RunPython.noop),
    ]
