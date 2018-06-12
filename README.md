# Setting up the Client for an OpenBench instance

## Windows
```
1) Obtain a working python3 installation
2) pip3 install requests
3) git clone https://github.com/AndyGrant/OpenBench.git
   OR simply download the repo from git (Harder to update!)

```

## Linux
```
1) sudo apt-get install python3
2) pip3 install requests
3) git clone https://github.com/AndyGrant/OpenBench.git
```


# Running the Client
```
# Username & Password from creating an account on the server
# Threads should be all cores minus one, or all hyper-threads minus two, at most
# Compiler will usually just be gcc/g++. This option allows support for gcc-versionX
# Profile uses PGO builds. Only enable if you are sure it gains speed, and is supported
python3 OpenBench.py -U username -P password -S server -T threads -C compiler -O profile
```

## Issues
```
Please report all issues here in this repo. OpenBench is still very much in development,
and issues are bound to occur. Differences in Operating System, bash/cmd interface, cutechess
compatibility issues, and many more are anticipated
```

# Setting up your own OpenBench instance

```
1) Obtain a working python3 installing
2) pip install Django=2.0.6
3) Run the ./cleanup.sh script
4) python3 manage.py createsuperuser
5) Run the ./run.sh script
6) You will want to create a non-superuser account
7) Go into the admin interface for the account, set enabled and approver flags
```

# Configuing OpenBench to use your Engine
```
1) In Client/OpenBench.py, adjust the NPS factor in completeWorkload()
   This value should be the NPS for a bench, on the desired scaling machine.
   I suggest that you scale this to match Fishtest's scaling
2) If your repo structure is not similar to Ethereal's, you will have to either
   change that, or modify the paths in getEngine() and buildEngine(). Additionally,
   if your makefile does not support CC=, you must change or modify this
3) In order to do scaling, your engine must support a bench command. OpenBench
   is currently configured to assume bench may be passed as a command line argument.
   The engine will run, report the final node count and nps, and then exit. You may
   need to update singleCoreBench() to handle the correct parsing of that output
4) Likely more steps to come. I plan to test with other engines once I am up and
   running at full capacity for Ethereal
```

## Things to avoid using, doing or modifying 
```
1) Threads=X MUST be in the options of ALL tests, for the time being
2) No spaces in option names or values. I could write the parsing code,
   but there really is NO reason to have spaces here. Shame on you.
3) More to come as I think of them and or realize my incompetency 
```
