# OpenBench

OpenBench is an open-source Chess Engine Testing Framework for UCI engines. OpenBench provides a lightweight interface and client to facilitate running fixed-game tests as well as SPRT tests to benchmark changes to engines for performance and stability. OpenBench supports [Fischer Random Chess](https://en.wikipedia.org/wiki/Chess960).

OpenBench is the primary testing framework used for the development of [Ethereal.](https://github.com/AndyGrant/Ethereal) The primary instance of OpenBench can be found at [http://chess.grantnet.us](http://chess.grantnet.us/). The Primary instance of OpenBench supports development for
[Berserk](https://github.com/jhonnold/berserk), [Bit-Genie](https://github.com/Aryan1508/Bit-Genie), [BlackMarlin](https://github.com/dsekercioglu/blackmarlin), [Demolito](https://github.com/lucasart/Demolito), [Drofa](https://github.com/justNo4b/Drofa), [Ethereal](https://github.com/AndyGrant/Ethereal), [FabChess](https://github.com/fabianvdW/FabChess), [Halogen](https://github.com/KierenP/Halogen), [Igel](https://github.com/vshcherbyna/igel), [Koivisto](https://github.com/Luecx/Koivisto), [Laser](https://github.com/jeffreyan11/laser-chess-engine), [RubiChess](https://github.com/Matthies/RubiChess), [Seer](https://github.com/connormcmonigle/seer-nnue), [Stash](https://github.com/mhouppin/stash-bot), [Weiss](https://github.com/TerjeKir/weiss), [Winter](https://github.com/rosenthj/Winter), and [Zahak](https://github.com/amanjpro/zahak). A dozen or more engines are using their own private, local instances of OpenBench.

You can join OpenBench's [Discord server](https://discord.com/invite/9MVg7fBTpM) to join the discussion, see what developers are working on and talking about, or to find out how you can contribute to the project and become a part of it. OpenBench is heavily inspired by [Fishtest](https://github.com/glinscott/fishtest). The project is powered by the [Django Web Framework](https://www.djangoproject.com/) and [Cutechess](https://github.com/cutechess/cutechess).


# The Client

The [OpenBench Client](https://github.com/AndyGrant/OpenBench/blob/master/Client/Client.py) is a ``python3`` script. The Client needs access to ``make`` and ``gcc``. Make is used to initiate builds for engines. Every engine on the framework will have a makefile in its repository. That makefile will execute a compiler, which is configured via OpenBench. When the Client is run, it will first check for compilers against the list of compilers requested by the engines on the framework. ``gcc`` is needed though, even if no C engines are on the framework, in order to determine CPU flags like POPCNT, AVX, AVX2, and more. For Windows users, a POSIX version of gcc is recommended.

The client takes four arguments: Username, Password, Server, Threads. First create an account via the instance's webpage. The instance will also be the Server provided to the client. Threads tells the Client how many games can be run in parallel. This should be no more than your CPU count. An example: ``python3 OpenBench.py -U username -P password -S http://chess.grantnet.us/ -T 8``

The client will create an ``Engines``, ``Books``, ``Networks``, and ``PGNs`` directory. These are used to store compiled engines, downloaded opening books, downloaded Networks, and PGNs of the games played. By default, Engines and PGNs are deleted after 24 hrs. Networks are deleted after a month. These durations can be changed directly in the Client in ``cleanup_client()``


# Engine Compliance with OpenBench

In order for many engines to operate under a shared framework, each engine must have uniform compliance in a small number of aspects. The following three paragraphs outline the standards expected by OpenBench.

Every test on OpenBench must have a ``Threads=`` and ``Hash=`` set in the UCI options. This is because the thread count plays a role in determining how many games to run in parallel. The Hash should, by default, be set to a low value. This is because when preparing an engine on the Client, benchmarks are run for each thread requested by the Client. A machine with 32 threads will run 32 copies of the engine at the same time during benching.

The engine must support being run from the command line with a sole argument, ``bench``. This should execute a series of low-depth searches on a set of positions. The resulting searches should be summed up, and a final Node count and Nodes Per Second value should be printed. In Ethereal, the final line of output before exiting contains ``3938740 nodes 1992281 nps``. The Node value is needed as a sort of checksum for the engine. The NPS value is needed in order to scale machines of differing speeds to one uniform time control.

The engine must have a makefile, with a default target that builds a single binary, whose name is determined by the ``EXE=`` argument. If the engine may be compiled with multiple compilers (such as supporting gcc & clang at the same time), then the ``CC=`` argument must also be accepted. Finally, engines with NNUE files must allow building via ``EVALFILE=``, which will compile the Network weights into the binary.

Lastly, an engine should play nice when closed by error, by Cutechess, by python, or by any other means. This can be verified by checking for hanging processes. Generally this is not an issue, but poor code for reading input pipes can cause this to occur. This is crucial, as the majority of machines connected to the main OpenBench instance are not constantly monitored.


# Adding an Engine to OpenBench

To add an engine to an existing OpenBench framework, all that must be done is to include an additional entry in the ``OPENBENCH_CONFIG`` dictionary located in ``OpenBench/config.py``. The entry for Ethereal looks like the following:

```
'Ethereal' : {

    'nps'    : 1200000,
    'base'   : 'master',
    'book'   : 'Pohl.epd',
    'bounds' : '[0.00, 5.00]',
    'source' : 'https://github.com/AndyGrant/Ethereal',

    'build' : {
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
```

The ``nps`` field is the speed of a single Ethereal process, when a copy is run on each thread of a machine at the same time. The value is subjective, and acts only to scale different machines to a uniform speed. The main OpenBench instance is scaled to the 16 threads of a Ryzen 3700x. ``Scripts/bench_engine.py`` allows you to simulate this process.

The ``base`` field refers to the base branch for testing. Generally, one will test against ``master``. New repositories default to ``main`` instead of ``master``, because of wokeness. This field is simply the default auto-filled value for creating a new test. It can be changed at any time.

The ``book`` field refers to the default opening book to be used. By default, OpenBench supports many different opening books, including fischer books, and double-fischer books.

The ``bounds`` field refers to the default SPRT bounds when creating a test. The first value is elo0, and the second value is elo1. Again, this is used to auto-fill test creation fields. It can be changed at any time.

The ``source`` field refers to the location of the repository that is being used. This is only used to set the links in the sidebar. Individual users set their own repositories for auto-filling test creation fields.

The ``path`` field refers to the location of the Makefile in the engine's repository. No leading or trailing slashes should be included.

The ``compilers`` field allows a list of compilers that are able to build the engine. Version requirements may be set as well. For example, ``['gcc>=8.0.0']`` would require the Client to have a gcc version at or above v8.0.0.

The ``cpuflags`` field allows a list of required CPU flags. Generally, this is not needed. Ethereal has these set just to make sure that all machines are able to run the NNUE at the fastest speeds. The option may be left as an empty list.
