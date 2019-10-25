OpenBench is an open-source sequential probability ratio testing framework designed for self-play testing by both UCI and XBOARD compliant engines written in C or C++. OpenBench provides a lightweight interface and client which allows machines to work together to test changes to the engine for performance, stability, or to just simply playing a large number of games. OpenBench currently has support for FRC/Chess960, and uses this variant when presented with an opening book containing "FRC" or "960".

OpenBench is the primary testing framework used for the development of [Ethereal.](https://github.com/AndyGrant/Ethereal) The primary instance of OpenBench can be found [here.](http://chess.grantnet.us/) This OpenBench instance currently supports development for [Ethereal](https://github.com/AndyGrant/Ethereal), as well as for [Laser](https://github.com/jeffreyan11/uci-chess-engine) and [Weiss](https://github.com/TerjeKir/weiss). Some engine authors are running their own public or private instances of OpenBench to support development for their engines. These other instances support engines of different origins, such as those written in Kotlin or Rust.

# Setting Up The Client For Windows

Install any version of [python3](https://www.python.org/downloads/)

Install any POSIX compliant version of [MinGW](https://sourceforge.net/projects/mingw-w64/files/Toolchains%20targetting%20Win64/Personal%20Builds/mingw-builds/6.3.0/threads-posix/)

Download a copy of the [OpenBench Client File](https://github.com/AndyGrant/OpenBench/blob/master/Client/OpenBench.py)

# Setting Up The Client For Linux

``sudo apt-get install python3 or yum install python3``

``sudo apt-get install gcc or yum install gcc``

``sudo apt-get install g++ or yum install g++``

Download a copy of the [OpenBench Client File](https://github.com/AndyGrant/OpenBench/blob/master/Client/OpenBench.py)

# Running The Client
The client takes four arguments: Username, Password, Server, Threads. First create an account via the instance's webpage. The instance will also be the Server provided to the client. Threads tells the Client how many games can be run in parallel. This should be no more than your CPU count minus one. For hyperthreaded machines, where hyperthreading support is strong, you may use all threads provided by CPU minus one cores. The following would connect to the main instance using 4 threads or CPUs.

``python3 OpenBench.py -U username -P password -S http://chess.grantnet.us/ -T 4``

# Engine Compliance with OpenBench

When ``./engine bench`` is run, the engine must provide a node count and nodes per second count after performing a search on some set of positions. The goal is that by making minor changes to the engine, the node count will vary. This acts as a hash for the engine. OpenBench assumes that the final two lines of output will be the node count, and the nodes per second count, respectively. Your engine should default to using a small amount of hash. This is because if a worker connects with 32 threads, it will run 32 benches in parallel.

OpenBench assumes that your make file can be found in ``/src/``. The make file will have ``EXE=<sha256>`` passed as the only argument, specificying the name of the produced binary. Your makefile should support a trivial build.

The options provided to the engines in all OpenBench tests must start with "Threads=X Hash=Y". Your engine should support a provided Hash value. If your engine does not support a variable number of Threads, [cutechess](https://github.com/cutechess/cutechess) will simply not pass on the information.

Your engine should play nice when closed by error, by cutechess, by python, or by any other means. This can be verified by checking for hanging processes. Generally this is not an issue, but poor code for reading input pipes can cause this to occur.

# Setting Up Your Own Instance

Add your engine to OpenBench/config.py, similar to [Ethereal's configuration.](https://github.com/AndyGrant/OpenBench/blob/1eb2dce5d5500df90a2ed85794cddf6cb509e299/OpenBench/config.py#L29-L40) The test modes are fairly standard, and are derived from those of [fishtest.](https://github.com/glinscott/fishtest) the NPS value is provided in order to scale CPUs of different speeds. Ethereal's speed is scaled to match the speed used by [Stockfish](https://github.com/official-stockfish). It is recommend to follow this scaling, so that the time controls have meaning without association with a particular CPU.

Create a user through the website, then through the Admin interface  (found at /admin from your server), enable your profile. You may also set yourself as an approver so that you may approve tests written by others. Additionally, to bypass the cross-approval mechanism, you may set yourself as a superuser.

# Running Your Own Instance

```
sudo apt-get install python3, pip3, git
pip3 install Django==2.0.6
pip3 install django-htmlmin
git clone https://github.com/AndyGrant/OpenBench
cd OpenBench
python3 manage.py makemigrations
python3 manage.py migrate
python3 manage.py migrate --run-syncdb
python3 manage.py createsuperuser
python3 manage.py runserver 127.0.0.1:8000
```