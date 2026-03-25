from OpenBench.models import *

from django.core.files.storage import FileSystemStorage
from django.forms.models import model_to_dict

def network_to_dict(network):
    return { **model_to_dict(network, exclude=['id']), 'created': str(network.created) }


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