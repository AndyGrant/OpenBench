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

USE_CROSS_APPROVAL = False

OPENBENCH_CONFIG = {

    'error' : {
        'disabled' : 'Account has not been enabled. Contact andrew@grantnet.us',
        'fakeuser' : 'This is not a real OpenBench User. Create an OpenBench account',
    },

    # Link to the repo on the sidebar, as well as the core files
    'framework' : 'http://github.com/AndyGrant/OpenBench/',
    'corefiles' : 'http://github.com/AndyGrant/OpenBench/raw/master/CoreFiles/',

    # SPRT Elo bounds and type I/II errors
    'sprt' : { 'elolower' : 0.00, 'eloupper' : 5.00, 'alpha' : 0.05, 'beta' : 0.05 },


    # Book confgiruation. When addding a book, follow the provided template.
    # The SHA is defined by hashlib.sha256(book).hexdigest(). Client.py has
    # code to generate and verify sha256 values, as an example.

    'books' : {

        '2moves_v1.epd' : {
            'name'    : '2moves_v1.epd',
            'sha'     : '7bec98239836f219dc41944a768c0506abed950aaec48da69a0782643e90f237',
            'source'  : 'http://github.com/AndyGrant/OpenBench/raw/master/Books/2moves_v1.epd.zip',
            'default' : False,
        },

        '8moves_v3.epd' : {
            'name'    : '8moves_v3.epd',
            'sha'     : '1f055af431656f09ee6a09d2448e0b876125f78bb7b404fca2031c403a1541e5',
            'source'  : 'http://github.com/AndyGrant/OpenBench/raw/master/Books/8moves_v3.epd.zip',
            'default' : False,
        },

        '3moves_FRC.epd' : {
            'name'    : '3moves_FRC.epd',
            'sha'     : '38d1b6c456bc3d3f69a4927e2667ef3f3fa231e253b6dc4040093f00a1c2ccb3',
            'source'  : 'http://github.com/AndyGrant/OpenBench/raw/master/Books/3moves_FRC.epd.zip',
            'default' : False,
        },

        '4moves_noob.epd' : {
            'name'    : '4moves_noob.epd',
            'sha'     : '4be746a91e3f8af0c9344b1e72d611e9fcfe486843867a55760970a4896f284d',
            'source'  : 'http://github.com/AndyGrant/OpenBench/raw/master/Books/4moves_noob.epd.zip',
            'default' : True,
        },
    },


    # Engine Configuration. All engines must have a name, a source repo,
    # a set of paramaters for each standard test type, as well as a scaled
    # NPS value, which is used to normalize speed across all workers.

    'engines'     : {

        'Ethereal' : {

            'nps'       : 640000,
            'source'    : 'https://github.com/AndyGrant/Ethereal',

            'build'     : {
                'path'      : 'src',
                'compilers' : ['gcc'],
                'cpuflags'  : ['AVX2', 'AVX', 'FMA', 'POPCNT', 'SSE2', 'SSE'],
            },

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '10.0+0.1' },
                'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
             },
        },

        'Laser' : {

            'nps'       : 720000,
            'source'    : 'https://github.com/jeffreyan11/uci-chess-engine',

            'build'     : {
                'path'      : 'src',
                'compilers' : ['g++'],
                'cpuflags'  : ['POPCNT'],
            },

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '10.0+0.1' },
                'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
             },
        },

        'Weiss' : {

            'nps'       : 2022000,
            'source'    : 'https://github.com/TerjeKir/weiss',

            'build'     : {
                'path'      : 'src',
                'compilers' : ['gcc'],
                'cpuflags'  : ['POPCNT'],
            },

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :  32, 'timecontrol' : '10.0+0.1' },
                'ltc'     : { 'threads' : 1, 'hash' : 128, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' : 128, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 512, 'timecontrol' : '20.0+0.2' },
            },
        },

        'Demolito' : {

            'nps'       : 1040000,
            'source'    : 'https://github.com/lucasart/Demolito',

            'build'     : {
                'path'      : 'src',
                'compilers' : ['clang', 'gcc'],
                'cpuflags'  : ['POPCNT'],
            },

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '8.0+0.08' },
                'ltc'     : { 'threads' : 1, 'hash' :  32, 'timecontrol' : '32.0+0.32'},
                'smpstc'  : { 'threads' : 8, 'hash' :  32, 'timecontrol' : '4.0+0.04' },
                'smpltc'  : { 'threads' : 8, 'hash' : 128, 'timecontrol' : '16.0+0.16'},
            },
        },

        'RubiChess' : {

            'nps'       : 1050000,
            'source'    : 'https://github.com/Matthies/RubiChess',

            'build'     : {
                'path'      : 'src',
                'compilers' : ['g++'],
                'cpuflags'  : ['POPCNT'],
            },

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '10.0+0.1' },
                'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
            },
        },

        'FabChess' : {

            'nps'       : 640000,
            'source'    : 'https://github.com/fabianvdW/FabChess',

            'build'     : {
                'path'      : '',
                'compilers' : ['cargo>=1.41.0'],
                'cpuflags'  : ['POPCNT'],
            },

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '10.0+0.1' },
                'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
            },
        },

        'Igel' : {

            'nps'       : 520000,
            'source'    : 'https://github.com/vshcherbyna/igel',

            'build'     : {
                'path'      : 'src',
                'compilers' : ['g++'],
                'cpuflags'  : ['POPCNT'],
            },

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '10.0+0.1' },
                'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
            },
        },

        'Winter' : {

            'nps'       : 465000,
            'source'    : 'https://github.com/rosenthj/Winter',

            'build'     : {
                'path'      : '',
                'compilers' : ['clang++', 'g++'],
                'cpuflags'  : ['POPCNT'],
            },

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '10.0+0.1' },
                'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
            },
        },

        'Halogen' : {

            'nps'       : 1320000,
            'source'    : 'https://github.com/KierenP/Halogen',

            'build'     : {
                'path'      : 'Halogen/src',
                'compilers' : ['g++'],
                'cpuflags'  : ['POPCNT'],
            },

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :   8, 'timecontrol' : '10.0+0.1' },
                'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
            },
        },

        'Stash' : {

            'nps'       : 1380000,
            'source'    : 'https://github.com/mhouppin/stash-bot',

            'build'     : {
                'path'      : 'src',
                'compilers' : ['gcc', 'clang'],
                'cpuflags'  : ['POPCNT'],
            },

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :  16, 'timecontrol' : '10.0+0.1' },
                'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
            },
        },
        
        'Seer' : {
            'nps'       : 500000,
            'source'    : 'https://github.com/connormcmonigle/seer-nnue.git',
            
            'build'     : { 
            	'path' : 'build',
            	'compilers' : ['g++'],
            	'cpuflags'  : ['AVX2', 'AVX', 'FMA', 'POPCNT', 'SSE2', 'SSE'], 
            },

            'testmodes' : {
                'stc'     : { 'threads' : 1, 'hash' :  32, 'timecontrol' : '15.0+0.15' },
                'ltc'     : { 'threads' : 1, 'hash' :  64, 'timecontrol' : '60.0+0.6' },
                'smpstc'  : { 'threads' : 8, 'hash' :  64, 'timecontrol' : '5.0+0.05' },
                'smpltc'  : { 'threads' : 8, 'hash' : 256, 'timecontrol' : '20.0+0.2' },
            },
        },
    },
}
