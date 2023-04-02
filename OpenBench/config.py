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

REQUIRE_LOGIN_TO_VIEW = True

REQUIRE_MANUAL_REGISTRATION = True

OPENBENCH_CONFIG = {

    # Server Client version control
    'client_version' : '7',

    # Generic Error Messages useful to those setting up their own instance
    'error' : {
        'disabled'            : 'Account has not been enabled. Contact andrew@grantnet.us',
        'fakeuser'            : 'This is not a real OpenBench User. Create an OpenBench account',
        'requires_login'      : 'All pages require a user login to access',
        'manual_registration' : 'Registration can only be done via an Administrator',
    },

    # Link to the repo on the sidebar, as well as the core files
    'framework' : 'http://github.com/AndyGrant/OpenBench/',
    'corefiles' : 'https://raw.githubusercontent.com/AndyGrant/OpenBench/master/CoreFiles',

    # Test Configuration. For both SPRT and Fixed Games Tests
    'tests' : {
        'max_games'  : '20000',        # Default for Fixed Games
        'confidence' : '[0.05, 0.05]', # SPRT Type I/II Confidence
    },

    # Book Configuration. When addding a book, follow the provided template.
    # The SHA is defined by hashlib.sha256(book.read().encode('utf-8')).hexdigest().
    # Client.py has this exact code to generate and verify sha256 values, as an example.

    'books' : {

        '2moves_v1.epd' : {
            'name'    : '2moves_v1.epd',
            'sha'     : '7bec98239836f219dc41944a768c0506abed950aaec48da69a0782643e90f237',
            'source'  : 'https://raw.githubusercontent.com/AndyGrant/OpenBench/master/Books/2moves_v1.epd.zip',
        },

        '8moves_v3.epd' : {
            'name'    : '8moves_v3.epd',
            'sha'     : '1f055af431656f09ee6a09d2448e0b876125f78bb7b404fca2031c403a1541e5',
            'source'  : 'https://raw.githubusercontent.com/AndyGrant/OpenBench/master/Books/8moves_v3.epd.zip',
        },

        '3moves_FRC.epd' : {
            'name'    : '3moves_FRC.epd',
            'sha'     : '6bf81e1ada6a3306bbc8356f7bca1e2984a2828d658799992d5443b7179c934d',
            'source'  : 'https://raw.githubusercontent.com/AndyGrant/OpenBench/master/Books/3moves_FRC.epd.zip',
        },

        '4moves_noob.epd' : {
            'name'    : '4moves_noob.epd',
            'sha'     : '4be746a91e3f8af0c9344b1e72d611e9fcfe486843867a55760970a4896f284d',
            'source'  : 'https://raw.githubusercontent.com/AndyGrant/OpenBench/master/Books/4moves_noob.epd.zip',
        },

        'Pohl.epd' : {
            'name'    : 'Pohl.epd',
            'sha'     : 'b3e64e0dab84cf451a9ac7ef031f5a2bbcf16c7e21be95298fb03cbf021f5466',
            'source'  : 'https://raw.githubusercontent.com/AndyGrant/OpenBench/master/Books/Pohl.epd.zip',
        },

        'Pohl.pgn' : {
            'name'    : 'Pohl.pgn',
            'sha'     : 'aaa7559c5d94e592fe5cca3586cb099d8fc5f13428d4ce84afc4b97811241c7e',
            'source'  : 'https://raw.githubusercontent.com/AndyGrant/OpenBench/master/Books/Pohl.pgn.zip',
        },

        'DFRC.epd' : {
            'name'    : 'DFRC.epd',
            'sha'     : '648c447ef40614a44d13b78911e81470d8ddb0d3b2711c1b180e990871f5db4f',
            'source'  : 'https://raw.githubusercontent.com/AndyGrant/OpenBench/master/Books/DFRC.epd.zip',
        },
    },


    # Engine Configuration. All engines must have a name, a source repo,
    # a set of paramaters for each standard test type, as well as a scaled
    # NPS value, which is used to normalize speed across all workers.

    'engines' : {

        'Ethereal' : {

            'nps'     : 1050000,
            'base'    : 'master',
            'book'    : 'Pohl.epd',
            'bounds'  : '[0.00, 3.00]',
            'source'  : 'https://github.com/AndyGrant/Ethereal',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : 'src',
                'compilers' : ['clang', 'gcc'],
                'cpuflags'  : ['__AVX2__', '__FMA__', '__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :   8, 'tc' : '10.0+0.1' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '60.0+0.6' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },

        'Laser' : {

            'nps'     : 935000,
            'base'    : 'master',
            'book'    : 'Pohl.epd',
            'bounds'  : '[0.00, 5.00]',
            'source'  : 'https://github.com/jeffreyan11/uci-chess-engine',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : 'src',
                'compilers' : ['g++'],
                'cpuflags'  : ['__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :   8, 'tc' : '8.0+0.08' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '40.0+0.4' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },

        'Weiss' : {

            'nps'     : 1700000,
            'base'    : 'master',
            'book'    : 'Pohl.epd',
            'bounds'  : '[-1.00, 4.00]',
            'source'  : 'https://github.com/TerjeKir/weiss',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : 'src',
                'compilers' : ['gcc'],
                'cpuflags'  : ['__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :  32, 'tc' : '8.0+0.08' },
                { 'id' : 'LTC',     'th' : 1, 'hash' : 128, 'tc' : '40.0+0.4' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' : 128, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 512, 'tc' : '20.0+0.2' },
            ],
        },

        'Demolito' : {

            'nps'     : 1300000,
            'base'    : 'master',
            'book'    : 'Pohl.epd',
            'bounds'  : '[0.00, 5.00]',
            'source'  : 'https://github.com/lucasart/Demolito',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : 'src',
                'compilers' : ['clang', 'gcc'],
                'cpuflags'  : ['__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :   8, 'tc' : '8.0+0.08' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  32, 'tc' : '32.0+0.32'},
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  32, 'tc' : '4.0+0.04' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 128, 'tc' : '16.0+0.16'},
            ],
        },

        'RubiChess' : {

            'nps'     : 925000,
            'base'    : 'master',
            'book'    : 'Pohl.epd',
            'bounds'  : '[0.00, 5.00]',
            'source'  : 'https://github.com/Matthies/RubiChess',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : 'src',
                'compilers' : ['g++'],
                'cpuflags'  : ['__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :   8, 'tc' : '10.0+0.1' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '60.0+0.6' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },

        'FabChess' : {

            'nps'     : 1000000,
            'base'    : 'master',
            'book'    : 'Pohl.epd',
            'bounds'  : '[0.00, 5.00]',
            'source'  : 'https://github.com/fabianvdW/FabChess',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : '',
                'compilers' : ['cargo>=1.41.0'],
                'cpuflags'  : ['__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :   8, 'tc' : '8.0+0.08' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '40.0+0.4' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },

        'Igel' : {

            'nps'     : 450000,
            'base'    : 'master',
            'book'    : 'Pohl.epd',
            'bounds'  : '[0.00, 3.00]',
            'source'  : 'https://github.com/vshcherbyna/igel',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : 'src',
                'compilers' : ['g++'],
                'cpuflags'  : ['__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :   8, 'tc' : '10.0+0.1' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '60.0+0.6' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },

        'Winter' : {

            'nps'     : 625000,
            'base'    : 'master',
            'book'    : 'Pohl.epd',
            'bounds'  : '[0.00, 5.00]',
            'source'  : 'https://github.com/rosenthj/Winter',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : '',
                'compilers' : ['clang++', 'g++'],
                'cpuflags'  : ['__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :   8, 'tc' : '8.0+0.08' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '40.0+0.4' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },

        'Halogen' : {

            'nps'     : 1800000,
            'base'    : 'master',
            'book'    : 'Pohl.epd',
            'bounds'  : '[0.00, 5.00]',
            'source'  : 'https://github.com/KierenP/Halogen',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : 'src',
                'compilers' : ['g++'],
                'cpuflags'  : ['__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :   8, 'tc' : '8.0+0.08' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '40.0+0.4' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },

        'Stash' : {

            'nps'     : 1625000,
            'base'    : 'master',
            'book'    : '4moves_noob.epd',
            'bounds'  : '[0.00, 5.00]',
            'source'  : 'https://github.com/mhouppin/stash-bot',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : 'src',
                'compilers' : ['gcc', 'clang'],
                'cpuflags'  : ['__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :  16, 'tc' : '8.0+0.08' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '40.0+0.4' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },

        'Seer' : {

            'nps'     : 875000,
            'base'    : 'main',
            'book'    : 'Pohl.epd',
            'bounds'  : '[0.00, 5.00]',
            'source'  : 'https://github.com/connormcmonigle/seer-nnue',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : 'build',
                'compilers' : ['g++>=9.0.0'],
                'cpuflags'  : ['__AVX2__', '__FMA__', '__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :  32, 'tc' : '8.0+0.08' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '40.0+0.4' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },

        'Koivisto' : {

            'nps'     : 1200000,
            'base'    : 'master',
            'book'    : 'Pohl.epd',
            'bounds'  : '[0.00, 2.50]',
            'source'  : 'https://github.com/Luecx/Koivisto',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : 'src_files',
                'compilers' : ['g++'],
                'cpuflags'  : ['__AVX2__', '__FMA__', '__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :   8, 'tc' : '8.0+0.08' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '40.0+0.4' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },

        'Drofa' : {

            'nps'     : 1250000,
            'base'    : 'master',
            'book'    : '4moves_noob.epd',
            'bounds'  : '[0.00, 5.00]',
            'source'  : 'https://github.com/justNo4b/Drofa',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : '',
                'compilers' : ['g++'],
                'cpuflags'  : ['__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :   8, 'tc' : '8.0+0.08' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '40.0+0.4' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },

        'Bit-Genie' : {

            'nps'     : 1975000,
            'base'    : 'master',
            'book'    : 'Pohl.epd',
            'bounds'  : '[0.00, 5.00]',
            'source'  : 'https://github.com/Aryan1508/Bit-Genie',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : 'src',
                'compilers' : ['g++'],
                'cpuflags'  : ['__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :   8, 'tc' : '8.0+0.08' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '40.0+0.4' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },

        'Berserk' : {

            'nps'     : 1325000,
            'base'    : 'main',
            'book'    : 'Pohl.epd',
            'bounds'  : '[0.00, 3.00]',
            'source'  : 'https://github.com/jhonnold/berserk',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : 'src',
                'compilers' : ['gcc'],
                'cpuflags'  : ['__AVX2__', '__FMA__', '__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :   8, 'tc' : '10.0+0.1' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '60.0+0.6' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },

        'Zahak' : {

            'nps'     : 850000,
            'base'    : 'master',
            'book'    : 'Pohl.epd',
            'bounds'  : '[0.00, 5.00]',
            'source'  : 'https://github.com/amanjpro/zahak',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : '',
                'compilers' : ['go'],
                'cpuflags'  : ['__AVX__', '__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :   8, 'tc' : '8.0+0.08' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '40.0+0.4' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },

        'BlackMarlin' : {

            'nps'     : 1075000,
            'base'    : 'main',
            'book'    : 'Pohl.epd',
            'bounds'  : '[0.00, 5.00]',
            'source'  : 'https://github.com/dsekercioglu/blackmarlin',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'     : '',
                'compilers': ['cargo>=1.57.0'],
                'cpuflags'  : ['__AVX2__', '__FMA__', '__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :   8, 'tc' : '8.0+0.08' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '40.0+0.4' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },

        '4ku' : {

            'nps'     : 1225000,
            'base'    : 'master',
            'book'    : 'Pohl.pgn',
            'bounds'  : '[0.00, 5.00]',
            'source'  : 'https://github.com/kz04px/4ku',
            'private' : False,

            'win_adj'  : 'movecount=3 score=400',
            'draw_adj' : 'movenumber=40 movecount=8 score=10',

            'build' : {
                'path'      : '',
                'compilers' : ['g++'],
                'cpuflags'  : ['__POPCNT__'],
            },

            'testmodes' : [
                { 'id' : 'STC',     'th' : 1, 'hash' :  64, 'tc' : '8.0+0.08' },
                { 'id' : 'LTC',     'th' : 1, 'hash' :  64, 'tc' : '40.0+0.4' },
                { 'id' : 'SMP STC', 'th' : 8, 'hash' :  64, 'tc' : '5.0+0.05' },
                { 'id' : 'SMP LTC', 'th' : 8, 'hash' : 256, 'tc' : '20.0+0.2' },
            ],
        },
    },
}
