import hashlib
import json
from collections.abc import Mapping
from contextvars import ContextVar

from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F


_request_revision = ContextVar('configuration_revision', default=None)


def current_revision():
    from OpenBench.models import ConfigurationRevision
    revision = _request_revision.get()
    if revision is None:
        revision = ConfigurationRevision.objects.first()
    if revision is None:
        raise ImproperlyConfigured('Run migrate to initialize OpenBench configuration. Use import_config --apply to recover a missing configuration revision.')
    return revision


class ConfigMapping(Mapping):
    def __getitem__(self, key):
        return current_revision().snapshot[key]

    def __iter__(self):
        return iter(current_revision().snapshot)

    def __len__(self):
        return len(current_revision().snapshot)


class ConfigurationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _request_revision.set(current_revision())
        try:
            return self.get_response(request)
        finally:
            _request_revision.reset(token)


def configuration_checksum():
    return current_revision().checksum


def configuration_user_enabled(actor):
    from OpenBench.models import Profile
    return bool(actor and actor.is_authenticated and actor.is_active and
        (actor.is_superuser or Profile.objects.filter(user=actor, enabled=True).exists()))


def can_manage_engine(actor, engine):
    return configuration_user_enabled(actor) and (actor.is_superuser or engine.maintainers.filter(user=actor).exists())


def authorize(instance, actor):
    from OpenBench.models import SiteSettings, EngineConfig, OpeningBook, WorkloadPreset
    if not configuration_user_enabled(actor) or type(instance) not in (SiteSettings, EngineConfig, OpeningBook, WorkloadPreset):
        raise PermissionDenied
    if actor.is_superuser:
        return
    if isinstance(instance, EngineConfig) and not instance._state.adding and can_manage_engine(actor, instance):
        return
    if isinstance(instance, WorkloadPreset):
        if instance.owner_id == actor.pk or (instance.owner_id is None and can_manage_engine(actor, instance.engine)):
            return
    raise PermissionDenied


def lock_settings(expected_generation):
    from OpenBench.models import SiteSettings
    updated = SiteSettings.objects.filter(pk=1, generation=expected_generation).update(generation=F('generation') + 1)
    if not updated:
        raise ValidationError('Configuration changed; reload before saving.')
    return SiteSettings.objects.get(pk=1)


def publish(site, actor, summary):
    from OpenBench.models import ConfigurationRevision, EngineConfig, OpeningBook
    snapshot = dict(site.settings, engines={}, books={entry.name: entry.settings for entry in OpeningBook.objects.filter(enabled=True)})
    for engine in EngineConfig.objects.filter(enabled=True).prefetch_related('presets'):
        settings = dict(engine.settings)
        snapshot['engines'][engine.name] = settings
        for field in ('test_presets', 'tune_presets', 'datagen_presets'):
            settings[field] = {'default': {}}
        for preset in engine.presets.all():
            if preset.owner_id is None:
                field = {'TEST': 'test_presets', 'TUNE': 'tune_presets', 'DATAGEN': 'datagen_presets'}[preset.workload_type]
                settings[field][preset.name] = preset.settings
    eligibility = {name: {key: data[key] for key in ('build', 'private', 'source')}
        for name, data in snapshot['engines'].items()}
    worker = {key: value for key, value in site.settings.items() if key.startswith(('client_', 'fastchess_'))}
    checksum = hashlib.sha256(json.dumps([eligibility, worker], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return ConfigurationRevision.objects.create(generation=site.generation, actor=actor, summary=summary,
        snapshot=snapshot, checksum=checksum)


@transaction.atomic
def save_configuration(instance, actor, expected_generation, maintainers=None):
    from OpenBench.models import SiteSettings, EngineConfig, OpeningBook, EngineMaintainer, Test
    authorize(instance, actor)
    if maintainers is not None and (not actor.is_superuser or not isinstance(instance, EngineConfig)):
        raise PermissionDenied
    site = lock_settings(expected_generation)
    if isinstance(instance, SiteSettings):
        instance.generation = site.generation
        site.settings = instance.settings
    elif not instance._state.adding:
        original = type(instance).objects.get(pk=instance.pk)
        authorize(original, actor)
        if original.name != instance.name:
            raise ValidationError('Names cannot change because existing workloads reference them.')
    if isinstance(instance, OpeningBook) and not instance.enabled:
        if Test.objects.filter(book_name=instance.name, finished=False, deleted=False).exists():
            raise ValidationError('Finish or delete workloads using this book before disabling it.')
    instance.full_clean()
    instance.save()
    if maintainers is not None:
        instance.maintainers.exclude(user__in=maintainers).delete()
        for user in maintainers:
            EngineMaintainer.objects.get_or_create(engine=instance, user=user)
    return publish(site, actor, 'Updated %s: %s' % (instance._meta.verbose_name, getattr(instance, 'name', 'site')))
