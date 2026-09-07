import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from OpenBench.configuration_schema import validate_book, validate_preset, validate_settings


class SiteSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    generation = models.PositiveBigIntegerField(default=0)
    settings = models.JSONField(default=dict)

    class Meta:
        constraints = [models.CheckConstraint(check=models.Q(id=1), name='single_site_settings')]

    def clean(self):
        validate_settings('site', self.settings)


class ConfigEntity(models.Model):
    name = models.CharField(max_length=64, unique=True, validators=[RegexValidator(r'^[^/\\\x00-\x1f]+$')])
    enabled = models.BooleanField(default=False)
    settings = models.JSONField(default=dict)

    class Meta:
        abstract = True
        ordering = ['name']

    def __str__(self):
        return self.name


class EngineConfig(ConfigEntity):
    def clean(self):
        validate_settings('engines', self.settings)
        if self.enabled:
            if self.settings['nps'] <= 0 or not self.settings['source'].startswith('https://') or not self.settings['build']['systems']:
                raise ValidationError('An enabled engine requires a source URL, positive NPS and an operating system.')
            if not self.settings['private'] and not self.settings['build']['compilers']:
                raise ValidationError('Public engines require a compiler.')


class OpeningBook(ConfigEntity):
    name = models.CharField(max_length=32, unique=True, validators=[RegexValidator(r'^[^/\\\x00-\x1f]+$')])

    def clean(self):
        validate_book(self.name, self.settings)


class EngineMaintainer(models.Model):
    engine = models.ForeignKey(EngineConfig, on_delete=models.CASCADE, related_name='maintainers')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['engine', 'user'], name='unique_engine_maintainer')]


class WorkloadPreset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    engine = models.ForeignKey(EngineConfig, on_delete=models.PROTECT, related_name='presets')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=128)
    workload_type = models.CharField(max_length=8, choices=[('TEST', 'Test'), ('TUNE', 'Tune'), ('DATAGEN', 'Datagen')])
    position = models.PositiveIntegerField(default=0)
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['position', 'name', 'id']
        constraints = [
            models.UniqueConstraint(fields=['engine', 'workload_type', 'name'], condition=models.Q(owner__isnull=True), name='unique_shared_preset'),
            models.UniqueConstraint(fields=['engine', 'owner', 'workload_type', 'name'], condition=models.Q(owner__isnull=False), name='unique_personal_preset'),
        ]

    def clean(self):
        validate_preset(self.workload_type, self.settings)


class ConfigurationRevision(models.Model):
    generation = models.PositiveBigIntegerField(primary_key=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(auto_now_add=True)
    summary = models.CharField(max_length=256)
    snapshot = models.JSONField()
    checksum = models.CharField(max_length=64)

    class Meta:
        ordering = ['-generation']
