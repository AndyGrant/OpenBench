from django import forms
from django.contrib.auth import get_user_model

from OpenBench.configuration_schema import SCHEMAS
from OpenBench.models import EngineConfig, OpeningBook, SiteSettings


class StringListField(forms.CharField):
    def to_python(self, value):
        return list(dict.fromkeys(line.strip() for line in (value or '').splitlines() if line.strip()))

    def prepare_value(self, value):
        return '\n'.join(value) if isinstance(value, list) else value


class ConfigurationForm(forms.Form):
    generation = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    def __init__(self, section, instance, generation, user, data=None):
        super().__init__(data=data, initial={'generation': generation})
        self.instance = instance
        self.schema = SCHEMAS[section]
        if not isinstance(instance, SiteSettings):
            self.fields['name'] = forms.CharField(max_length=instance._meta.get_field('name').max_length,
                initial=instance.name, disabled=not instance._state.adding)
            self.fields['enabled'] = forms.BooleanField(required=False, initial=instance.enabled)
        self.add_settings(self.schema, instance.settings)
        if isinstance(instance, EngineConfig) and user.is_superuser:
            self.fields['maintainers'] = forms.ModelMultipleChoiceField(get_user_model().objects.filter(is_active=True).order_by('username'),
                required=False, widget=forms.CheckboxSelectMultiple,
                initial=instance.maintainers.values_list('user_id', flat=True) if not instance._state.adding else [])
        labels = {'nps': 'Reference NPS', 'private': 'Private engine', 'build__path': 'Build directory',
            'build__compilers': 'Compilers', 'build__systems': 'Operating systems', 'build__cpuflags': 'Required CPU features',
            'sha': 'Book SHA-256', 'source': 'Download URL' if isinstance(instance, OpeningBook) else 'Repository URL'}
        for name, label in labels.items():
            if name in self.fields:
                self.fields[name].label = label
        if 'nps' in self.fields and self.fields['nps'].initial is None:
            self.fields['nps'].initial = 0
        if 'format' in self.fields:
            self.fields['format'].initial = instance.settings.get('format', instance.name.rsplit('.', 1)[-1])

    def columns(self):
        definitions = [
            ('Identity', ('name', 'enabled', 'source', 'private')),
            ('Performance & build', ('nps', 'build__path', 'build__compilers', 'build__systems', 'build__cpuflags')),
            ('Opening data', ('format', 'sha')),
            ('Maintainers', ('maintainers',)),
            ('Access & approvals', ('require_login_to_view', 'require_manual_registration', 'use_cross_approval')),
            ('Worker updates', ('client_version', 'client_repo_url', 'client_repo_ref', 'fastchess_min_version', 'fastchess_repo_url', 'fastchess_repo_ref')),
            ('Scheduling & downloads', ('balance_engine_throughputs', 'use_x_accel_redirect', 'x_accel_redirect_root')),
        ]
        groups = [(title, [self[name] for name in names if name in self.fields]) for title, names in definitions]
        groups = [(title, fields) for title, fields in groups if fields]
        midpoint = (len(groups) + 1) // 2
        return [column for column in (groups[:midpoint], groups[midpoint:]) if column]

    def add_settings(self, schema, values, prefix=''):
        for key, spec in schema['properties'].items():
            name = prefix + key
            if 'properties' in spec:
                self.add_settings(spec, values.get(key, {}), name + '__')
                continue
            options = {'label': name.replace('__', ' / ').replace('_', ' ').capitalize(), 'initial': values.get(key)}
            if 'enum' in spec:
                field = forms.ChoiceField(choices=[(value, value) for value in spec['enum']], **options)
            elif spec['type'] == 'boolean':
                field = forms.BooleanField(required=False, **options)
            elif spec['type'] == 'integer':
                field = forms.IntegerField(min_value=spec.get('minimum', 0), **options)
            elif spec['type'] == 'array':
                field = StringListField(required=False, widget=forms.Textarea(attrs={'rows': 2}), **options)
            else:
                field = forms.CharField(required=bool(spec.get('minLength') or spec.get('pattern')), **options)
            self.fields[name] = field

    def settings_data(self, schema, prefix=''):
        return {key: self.settings_data(spec, prefix + key + '__') if 'properties' in spec else self.cleaned_data[prefix + key]
            for key, spec in schema['properties'].items()}

    def populate(self):
        for field in ('name', 'enabled'):
            if field in self.cleaned_data:
                setattr(self.instance, field, self.cleaned_data[field])
        self.instance.settings = self.settings_data(self.schema)
        return self.instance
