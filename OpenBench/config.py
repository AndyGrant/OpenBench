# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                             #
#   OpenBench is a chess engine testing framework authored by Andrew Grant.   #
#   <https://github.com/AndyGrant/OpenBench>           <andrew@grantnet.us>   #
#                                                                             #
#   OpenBench is free software: you can redistribute it and/or modify         #
#   it under the terms of the GNU General Public License as published by      #
#   the Free Software Foundation, either version 3 of the License, or         #
#   (at your option) any later version.                                       #
#                                                                             #
#   OpenBench is distributed in the hope that it will be useful,              #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of            #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             #
#   GNU General Public License for more details.                              #
#                                                                             #
#   You should have received a copy of the GNU General Public License         #
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.     #
#                                                                             #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

OPENBENCH_CONFIG = {

    'error' : {
        'disabled' : 'Account has not been enabled. Contact andrew@grantnet.us',
        'fakeuser' : 'This is not a real OpenBench User. Create an OpenBench account',
    },


    # Link to the repo on the sidebar, as well as the core files
    'framework'   : 'http://github.com/AndyGrant/OpenBench/',
    'corefiles'   : 'http://github.com/AndyGrant/OpenBench/raw/master/CoreFiles/',

    # SPRT Elo bounds and type I/II errors
    'sprt' : { 'elolower' : 0.00, 'eloupper' : 5.00, 'alpha' : 0.05, 'beta' : 0.05 },


    # Book confgiruation. When addding a book, follow the provided template.
    # The SHA is defined by hashlib.sha256(book).hexdigest(). OpenBench.py
    # (Client File) has an example to show you how to find a hash digest

    'books' : {

        '2moves_v1.pgn' : {
            'name'    : '2moves_v1.pgn',
            'sha'     : '46aed7f2696618b2b914942032957b7a97a8f343bf54ba83e20a47818f0d42e0',
            'source'  : 'http://github.com/AndyGrant/OpenBench/raw/master/Books/2moves_v1.pgn',
            'default' : False,
        },

        '8moves_v3.pgn' : {
            'name'    : '8moves_v3.pgn',
            'sha'     : '04fcce1488a94f3b7795cef6f74d89016eb278328897c1018e6162c5967273f5',
            'source'  : 'http://github.com/AndyGrant/OpenBench/raw/master/Books/8moves_v3.pgn',
            'default' : False,
        },

        '3moves_FRC.pgn' : {
            'name'    : '3moves_FRC.pgn',
            'sha'     : '4c801140e3a52d3a306cb226ccd6225c47789409c5f2d0e1d7cf86152ea1f973',
            'source'  : 'http://github.com/AndyGrant/OpenBench/raw/master/Books/3moves_FRC.pgn',
            'default' : False,
        },

        '4moves_noob.pgn' : {
            'name'    : '4moves_noob.pgn',
            'sha'     : '377c0eef1d4b291ece226da89d8f7e8000396ca836abcb84f733417c31916664',
            'source'  : 'http://github.com/AndyGrant/OpenBench/raw/master/Books/4moves_noob.pgn',
            'default' : True,
        },
    },


    # Engine Configuration. All engines must have a name, a source repo,
    # a set of paramaters for each standard test type, as well as a scaled
    # NPS value, which is used to normalize speed across all workers.

    'engines'     : {

        'Ethereal' : {

            'proto'     : 'uci',
            'nps'       : 1275000,
            'build'     : { 'path' : '/src/', 'compilers' : ['gcc'] },
            'source'    : 'https://github.com/AndyGrant/Ethereal',

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '12.0+0.12' },
                'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
             },
        },

        'Laser' : {

            'proto'     : 'uci',
            'nps'       : 710000,
            'build'     : { 'path' : '/src/', 'compilers' : ['g++'] },
            'source'    : 'https://github.com/jeffreyan11/uci-chess-engine',

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '10.0+0.1' },
                'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
             },
        },

        'Weiss' : {

            'proto'     : 'uci',
            'nps'       : 2675000,
            'build'     : { 'path' : '/src/', 'compilers' : ['gcc'] },
            'source'    : 'https://github.com/TerjeKir/weiss',

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :  32, 'timecontrol' : '10.0+0.1' },
                'ltc'     : { 'threads' : 1, 'hash' : 128, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' : 128, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 512, 'timecontrol' : '20.0+0.2' },
            },
        },

        'Demolito' : {

            'proto'     : 'uci',
            'nps'       : 1250000,
            'build'     : { 'path' : '/src/', 'compilers' : ['clang', 'gcc'] },
            'source'    : 'https://github.com/lucasart/Demolito',

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '8.0+0.08' },
                'ltc'     : { 'threads' : 1, 'hash' :  32, 'timecontrol' : '32.0+0.32'},
                'smpstc'  : { 'threads' : 8, 'hash' :  32, 'timecontrol' : '4.0+0.04' },
                'smpltc'  : { 'threads' : 8, 'hash' : 128, 'timecontrol' : '16.0+0.16'},
            },
        },

        'RubiChess' : {

            'proto'     : 'uci',
            'nps'       : 1000000,
            'build'     : { 'path' : '/src/', 'compilers' : ['g++'] },
            'source'    : 'https://github.com/Matthies/RubiChess',

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '10.0+0.1' },
                'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
            },
        },

        'FabChess' : {

            'proto'     : 'uci',
            'nps'       : 640000,
            'build'     : { 'path' : '', 'compilers' : ['cargo>=1.41.0'] },
            'source'    : 'https://github.com/fabianvdW/FabChess',

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '10.0+0.1' },
                'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
            },
        },

        'Igel' : {

            'proto'     : 'uci',
            'nps'       : 885000,
            'build'     : { 'path' : '/src/', 'compilers' : ['g++'] },
            'source'    : 'https://github.com/vshcherbyna/igel',

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '10.0+0.1' },
                'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
            },
        },

        'Winter' : {

            'proto'     : 'uci',
            'nps'       : 370000,
            'build'     : { 'path' : '/', 'compilers' : ['clang++', 'g++'] },
            'source'    : 'https://github.com/rosenthj/Winter',

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '10.0+0.1' },
                'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
            },
        },
    },
}
