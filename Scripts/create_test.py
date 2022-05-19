import requests

# Basic Information:
# Test options must contain 'Threads={} Hash={}'
# Test Modes may either be of type 'SPRT' or 'GAMES'
# Syzygy settings are { 'OPTIONAL', 'REQUIRED', 'DISABLED' }
# Max Games is ignored unless test is of type 'GAMES'
# Networks must be assigned using their SHA256, not their name
# Networks with the value '' are used for tests without Networks

URL = 'http://chess.grantnet.us/scripts/'

data = {

    'enginename'  : '',
    'source'      : '',

    'devbench'    : '',
    'devbranch'   : '',
    'devoptions'  : '',
    'devnetwork'  : '',

    'basebench'   : '',
    'basebranch'  : '',
    'baseoptions' : '',
    'basenetwork' : '',

    'bookname'    : '',
    'timecontrol' : '',

    'test_mode'   : '',
    'bounds'      : '',
    'confidence'  : '',
    'max_games'   : '',

    'priority'    : '',
    'throughput'  : '',
    'syzygy_adj'  : '',
    'syzygy_wdl'  : '',

    'username'    : '',
    'password'    : '',
    'action'      : 'CREATE_TEST',
}

r = requests.post(URL, data=data)

print(r.text)