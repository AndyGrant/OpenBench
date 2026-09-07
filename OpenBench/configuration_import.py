import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction

from OpenBench.configuration import lock_settings, publish
from OpenBench.configuration_schema import DEFAULT_SITE, validate_book, validate_preset, validate_settings


def read_legacy_config(directory):
    root = Path(directory).resolve()

    def read(folder, name):
        path = (root / folder / name).resolve()
        if not path.is_relative_to(root / folder):
            raise ValidationError('Configuration path escapes its directory.')
        with path.open(encoding='utf-8-sig') as stream:
            return json.load(stream)

    original = read('Config', 'config.json')
    site = {key: value for key, value in original.items() if key not in ('engines', 'books')}
    validate_settings('site', site)
    bundle = {'site': site}
    for section, folder in (('engines', 'Engines'), ('books', 'Books')):
        names = original[section]
        max_length = 64 if section == 'engines' else 32
        if not isinstance(names, list) or any(not isinstance(name, str) or not name or len(name) > max_length for name in names):
            raise ValidationError('%s must be a list of names of at most %d characters.' % (section, max_length))
        if len(names) != len(set(names)):
            raise ValidationError('Duplicate %s names.' % section)
        bundle[section] = {}
        for name in names:
            settings = read(folder, name + '.json')
            presets = {}
            if section == 'engines':
                for field, kind in (('test_presets', 'TEST'), ('tune_presets', 'TUNE'), ('datagen_presets', 'DATAGEN')):
                    entries = settings.pop(field, {'default': {}})
                    defaults = entries.get('default', {})
                    presets[kind] = {}
                    for preset, values in entries.items():
                        resolved = defaults | values
                        validate_preset(kind, resolved)
                        presets[kind][preset] = resolved
            else:
                settings.setdefault('format', name.rsplit('.', 1)[-1].lower())
                validate_book(name, settings)
            validate_settings(section, settings)
            bundle[section][name] = {'settings': settings, 'presets': presets}
    return bundle


@transaction.atomic
def import_legacy_config(bundle, replace=False):
    from OpenBench.models import SiteSettings, EngineConfig, OpeningBook, WorkloadPreset
    SiteSettings.objects.get_or_create(pk=1, defaults={'settings': DEFAULT_SITE})
    generation = SiteSettings.objects.values_list('generation', flat=True).get(pk=1)
    site = lock_settings(generation)
    if generation and not replace:
        raise ValidationError('Configuration already exists; use --replace to update imported entries and site settings.')
    site.settings = bundle['site']
    site.full_clean()
    site.save(update_fields=['settings'])
    for section, model in (('engines', EngineConfig), ('books', OpeningBook)):
        for name, data in bundle[section].items():
            instance = model.objects.filter(name=name).first() or model(name=name)
            instance.settings = data['settings']
            instance.enabled = True
            instance.full_clean()
            instance.save()
            for kind, presets in data['presets'].items():
                if replace:
                    instance.presets.filter(owner=None, workload_type=kind).exclude(name__in=presets).delete()
                for position, (name, settings) in enumerate(presets.items()):
                    preset = WorkloadPreset.objects.filter(engine=instance, owner=None, workload_type=kind, name=name).first()
                    preset = preset or WorkloadPreset(engine=instance, workload_type=kind, name=name)
                    preset.settings, preset.position = settings, position
                    preset.full_clean()
                    preset.save()
    return publish(site, None, 'Imported JSON configuration')
