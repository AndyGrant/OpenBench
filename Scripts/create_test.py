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

    'dev_engine'       : '',
    'dev_repo'         : '',
    'dev_branch'       : '',
    'dev_bench'        : '',
    'dev_network'      : '',
    'dev_options'      : 'Threads=1 Hash=16',
    'dev_time_control' : '8.0+0.08',

    'base_engine'      : '',
    'base_repo'        : '',
    'base_branch'      : '',
    'base_bench'       : '',
    'base_network'     : '',
    'base_options'     : 'Threads=1 Hash=16',
    'base_time_control': '8.0+0.08',

    'test_mode'        : 'GAMES',
    'test_bounds'      : 'N/A',
    'test_confidence'  : 'N/A',
    'test_max_games'   : '',

    'book_name'        : 'UHO_Lichess_4852_v1.epd',
    'upload_pgns'      : 'FALSE',
    'throughput'       : '1000',
    'workload_size'    : '32',
    'priority'         : '0',

    'syzygy_wdl'       : 'DISABLED',
    'syzygy_adj'       : 'OPTIONAL',

    'win_adj'          : 'movecount=3 score=400',
    'draw_adj'         : 'movenumber=30 movecount=6 score=10',

    'scale_method'     : 'BASE',
    'scale_nps'        : '1000000',

    'info'             : '',

    'username'         : '',
    'password'         : '',
    'action'           : 'CREATE_TEST',
}

r = requests.post(URL, data=data)

print(r.text)