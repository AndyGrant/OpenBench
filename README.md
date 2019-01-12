# Setting up the Client for an OpenBench instance

## Windows
```
1) Obtain a working python3 installation
2) download https://github.com/AndyGrant/OpenBench/blob/master/Client/OpenBench.py
3) Move OpenBench.py to its own directory
```

## Linux
```
1) sudo apt-get install python3
2) git clone https://github.com/AndyGrant/OpenBench.git
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
2) pip3 install -r requirements.txt
3) Run the ./cleanup.sh script
4) python3 manage.py createsuperuser
5) Run the ./run.sh script
6) You will want to create a non-superuser account
7) Go into the admin interface for the account, set enabled and approver flags
```

# Configuing OpenBench to use your Engine
```
In OpenBench/config.py, add your Engine to the engines list. Follow the defined
template, which explains how to determine the NPS factor for your engine
```

## Things to avoid using, doing or modifying 
```
1) Threads=X MUST be in the options of ALL tests, for the time being
2) No spaces in option names or values. I could write the parsing code,
   but there really is NO reason to have spaces here. Shame on you.
3) More to come as I think of them and or realize my incompetency 
```
