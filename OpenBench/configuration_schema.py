from django.core.exceptions import ValidationError
from jsonschema import Draft202012Validator


DEFAULT_SITE = {
    'client_version': 50,
    'client_repo_url': 'https://github.com/AndyGrant/OpenBench',
    'client_repo_ref': 'master',
    'fastchess_min_version': '1.8.1',
    'fastchess_repo_url': 'https://github.com/AndyGrant/fastchess',
    'fastchess_repo_ref': 'master',
    'use_cross_approval': False,
    'require_login_to_view': False,
    'require_manual_registration': False,
    'balance_engine_throughputs': False,
    'use_x_accel_redirect': False,
    'x_accel_redirect_root': '/x-accel-media/',
}


def document(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


STRING = {'type': 'string'}
URL = {'type': 'string', 'pattern': r'^https://[^\s]+$'}
STRINGS = {'type': 'array', 'items': STRING, 'uniqueItems': True}
SCHEMAS = {
    'site': document({key: {'type': 'boolean' if type(value) is bool else 'integer' if type(value) is int else 'string'}
        for key, value in DEFAULT_SITE.items()}),
    'engines': document({
        'private': {'type': 'boolean'}, 'nps': {'type': 'integer', 'minimum': 0}, 'source': STRING,
        'build': document({'path': STRING, 'compilers': STRINGS, 'cpuflags': STRINGS,
            'systems': STRINGS}),
    }),
    'books': document({'source': URL, 'sha': {'type': 'string', 'pattern': r'^[a-fA-F0-9]{64}$'}}),
}
SCHEMAS['books']['properties']['format'] = {'enum': ['epd', 'pgn']}
for key in ('client_repo_url', 'fastchess_repo_url'):
    SCHEMAS['site']['properties'][key] = URL
for key in ('client_repo_ref', 'fastchess_repo_ref', 'fastchess_min_version'):
    SCHEMAS['site']['properties'][key] = dict(STRING, minLength=1)
SCHEMAS['site']['properties']['client_version']['minimum'] = 1
SCHEMAS['site']['properties']['x_accel_redirect_root'] = dict(STRING, pattern=r'^/')


def validate_settings(section, value):
    errors = list(Draft202012Validator(SCHEMAS[section]).iter_errors(value))
    if errors:
        raise ValidationError(['%s: %s' % ('.'.join(map(str, error.path)) or section, error.message) for error in errors])


def validate_book(name, value):
    validate_settings('books', value)
    suffix = name.rsplit('.', 1)[-1] if '.' in name else ''
    if suffix not in ('epd', 'pgn'):
        raise ValidationError('Book names must end in .epd or .pgn for worker compatibility.')
    if value.get('format', suffix) != suffix:
        raise ValidationError('Book format must match the filename extension.')


def validate_preset(kind, value):
    from OpenBench.config import verify_engine_test_preset, verify_engine_tune_preset, verify_engine_datagen_preset
    validators = {'TEST': verify_engine_test_preset, 'TUNE': verify_engine_tune_preset, 'DATAGEN': verify_engine_datagen_preset}
    if kind not in validators or not isinstance(value, dict):
        raise ValidationError('Invalid preset settings.')
    if any(type(item) not in (str, int, float, bool) for item in value.values()):
        raise ValidationError('Preset fields must contain scalar values.')
    try:
        validators[kind](value)
    except Exception as error:
        raise ValidationError(str(error)) from error
