FRAMEWORK_REPO_URL = 'http://github.com/AndyGrant/OpenBench/'

FRAMEWORK_DEFAULTS = {

    'config' : {

        # Framework source, must be changed for your instance
        'framework'   : 'http://github.com/AndyGrant/OpenBench/',

        # Default to uci since everyone uses it
        'protocol'    : 'uci',

        # Defaults for Short Time Control tests
        'stc'         : {
            'threads'     : 1,
            'hash'        : 8,
            'timecontrol' : '10.0+0.1',
        },

        # Defaults for Long Time Control tests
        'ltc'         : {
            'threads'     : 1,
            'hash'        : 64,
            'timecontrol' : '60.0+0.6',
        },

        # Defaults for Short Time Control tests with SMP
        'smpstc'      : {
            'threads'     : 8,
            'hash'        : 64,
            'timecontrol' : '5.0+0.05',
        },

        # Defaults for Long Time Control tests with SMP
        'smpltc'      : {
            'threads'     : 8,
            'hash'        : 256,
            'timecontrol' : '20.0+0.2',
        },

        # SPRT bounds and confidence values
        'elolower'    : 0.0,
        'eloupper'    : 5.0,
        'alpha'       : 0.05,
        'beta'        : 0.05,

        # Configured engines for the framework. To scale NPS for your engine,
        # in order to match the time controls used here, do the following.
        # Average a few bench runs for the latest version of Ethereal. Now
        # take a few bench runs for the latest version of the new engine.
        # Scale your NPS to match Ethereal's NPS of 1,500,000

        'engines'     : {
            'Ethereal' : {
                'name'    : 'Ethereal',
                'source'  : 'https://github.com/AndyGrant/Ethereal',
                'nps'     : 1500000,
                'default' : True,
            },

            'Laser' : {
                'name'    : 'Laser',
                'source'  : 'https://github.com/jeffreyan11/uci-chess-engine',
                'nps'     : 625000,
                'default' : False,
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
