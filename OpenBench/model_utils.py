from OpenBench.models import *

from django.core.files.storage import FileSystemStorage
from django.forms.models import model_to_dict

def network_to_dict(network):
    return { **model_to_dict(network, exclude=['id']), 'created': str(network.created) }

def engine_to_dict(engine):
    return { 'id': engine.id, **model_to_dict(engine, exclude=['id']) }

def ordered_presets(presets):

    # The internal binary representation of JSON objects used by MySQL's JSON
    # type (and PostgreSQL's jsonb, etc.) normalizes and sorts object keys,
    # losing the original order in which they were presented.
    # To avoid shuffling, store the intended order alongside the presets.
    return {
        **presets,
        '_preset_order' : {
            preset_type : list(group.keys())
            for preset_type, group in presets.items()
            if preset_type != '_preset_order' and isinstance(group, dict)
        },
    }

def restore_preset_order(config):

    presets = dict(config.presets or {})
    order   = presets.pop('_preset_order', {})

    ordered = {}
    for preset_type, group in presets.items():

        if not isinstance(group, dict):
            ordered[preset_type] = group
            continue

        names = [name for name in order.get(preset_type, []) if name in group]
        names += [name for name in group if name not in names]

        ordered[preset_type] = { name : group[name] for name in names }

    return ordered

def engine_config_to_dict(config):

    # Matches the shape of the Engines/<name>.json files these replaced
    return {
        'private' : config.private,
        'nps'     : config.nps,
        'source'  : config.source,
        'build'   : config.build(),
        **restore_preset_order(config),
    }

def workload_to_dict(workload):

    # dev/base are dumped as nested Engine dicts; the trinomial and pentanomial
    # counters are regrouped into tuples. Everything else is dumped verbatim.
    nested = ['dev', 'base', 'losses', 'draws', 'wins', 'LL', 'LD', 'DD', 'DW', 'WW']

    return {
        'id'       : workload.id,
        **model_to_dict(workload, exclude=['id'] + nested),
        'dev'      : engine_to_dict(workload.dev),
        'base'     : engine_to_dict(workload.base),
        'tri'      : workload.as_tri(),
        'penta'    : workload.as_penta(),
        'creation' : str(workload.creation),
        'updated'  : str(workload.updated),
    }

def network_delete(network) -> (str, bool):

    # Don't allow deletion of important networks
    if network.default or network.was_default:
        return 'You may not delete Default, or previous Default networks', False

    # Save information before deleting the Network Model
    status = 'Deleted %s for %s' % (network.name, network.engine)
    sha256 = network.sha256; network.delete()

    # Only delete the actual file if no other engines use it
    if not Network.objects.filter(sha256=sha256):
        FileSystemStorage().delete(sha256)
        FileSystemStorage().delete('%s.zst' % (sha256))

    return status, True
