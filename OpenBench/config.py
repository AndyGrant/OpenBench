
# Workers will use FRAMEWORK_REPO_URL to determine the location
# for the Cutechess binary and DLLs, as well as any of the books
# which are being used in the testing framework. The main OpenBench
# repo should suffice, but new books require this to be redirected.
FRAMEWORK_REPO_URL = 'http://github.com/AndyGrant/OpenBench/'

FRAMEWORK_DEFAULTS = {

    'config' : {

        # Controls the Link on the sidebar
        'framework'   : FRAMEWORK_REPO_URL,

        # Email of OpenBench instance owner
        'serveradmin' : 'andrew@grantnet.us',

        # SPRT Elo bounds and type I/II errors
        'sprt' : {
            'elolower' : 0.00, 'eloupper' : 5.00,
            'alpha'    : 0.05, 'beta'     : 0.05,
        },

        # Engine Configuration. All engines must have a name, a source repo,
        # a set of paramaters for each standard test type, as well as a scaled
        # NPS value, which is used to normalize speed across all workers.

        'engines'     : {
            'Ethereal' : {
                'proto'     : 'uci',
                'nps'       : 1500000,
                'name'      : 'Ethereal',
                'source'    : 'https://github.com/AndyGrant/Ethereal',
                'testmodes' : {
                    'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '10.0+0.1' },
                    'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                    'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                    'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
                 },
            },

            'Laser' : {
                'proto'   : 'uci',
                'nps'     : 625000,
                'name'    : 'Laser',
                'source'  : 'https://github.com/jeffreyan11/uci-chess-engine',
                'testmodes' : {
                    'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '10.0+0.1' },
                    'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                    'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                    'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
                 },
            },

            'Weiss' : {
                'proto'   : 'uci',
                'nps'     : 4000000,
                'name'    : 'Weiss',
                'source'  : 'https://github.com/TerjeKir/weiss',
                'testmodes' : {
                    'stc'     : { 'threads' : 1, 'hash' :  32, 'timecontrol' : '10.0+0.1' },
                    'ltc'     : { 'threads' : 1, 'hash' : 128, 'timecontrol' : '60.0+0.6' },
                    'smpstc'  : { 'threads' : 8, 'hash' : 128, 'timecontrol' : '5.0+0.05' },
                    'smpltc'  : { 'threads' : 8, 'hash' : 512, 'timecontrol' : '20.0+0.2' },
                },
            },
        },

        # Book confgiruation. When addding a book, follow the provided template.
        # The SHA is defined by hashlib.sha256(book).hexdigest(). OpenBench.py
        # (Client File) has an example to show you how to find a hash digest

        'books' : {
            '2moves_v1.pgn' : {
                'name'    : '2moves_v1.pgn',
                'sha'     : '46aed7f2696618b2b914942032957b7a97a8f343bf54ba83e20a47818f0d42e0',
                'source'  : FRAMEWORK_REPO_URL + 'raw/master/Books/2moves_v1.pgn',
                'default' : True,
            },

            '8moves_v3.pgn' : {
                'name'    : '8moves_v3.pgn',
                'sha'     : '04fcce1488a94f3b7795cef6f74d89016eb278328897c1018e6162c5967273f5',
                'source'  : FRAMEWORK_REPO_URL + 'raw/master/Books/8moves_v3.pgn',
                'default' : False,
            },

            '3moves_FRC.pgn' : {
                'name'    : '3moves_FRC.pgn',
                'sha'     : '4c801140e3a52d3a306cb226ccd6225c47789409c5f2d0e1d7cf86152ea1f973',
                'source'  : FRAMEWORK_REPO_URL + 'raw/master/Books/3moves_FRC.pgn',
                'default' : False,
            },
        },
    }
}
