from OpenBench.models import *

from django.core.files.storage import FileSystemStorage
from django.forms.models import model_to_dict

def network_to_dict(network):
    return { **model_to_dict(network, exclude=['id']), 'created': str(network.created) }

def engine_to_dict(engine):
    return { 'id': engine.id, **model_to_dict(engine, exclude=['id']) }

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

    return status, True
