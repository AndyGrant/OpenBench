OpenBench Client

This repository contains the client application for connecting to OpenBench, a platform for running benchmarks and tests. Follow the steps below to set up and run the client.
Prerequisites

    Python 3.x
    Git

Installation

    Clone the repository:

    bash

git clone https://github.com/AndyGrant/OpenBench

Change directory to the client folder:

bash

cd OpenBench/Client

Install dependencies using pip:

bash

    pip install -r requirements.txt

Usage

Once the installation is complete, you can run the client using the following command:

bash

    python3 client.py --server <server url> --username <OBUsername> --password <OBPass> --threads 'Number of threads' --nsockets 'cutechess instances' --fleet

Make sure to replace 'server url', 'OBUsername', 'OBPass', 'num_threads', and 'num_cutechess_instances' with appropriate values. Additionally, the --fleet flag should be set if you need to run in fleet mode. Refer to the OpenBench Wiki for more context on fleet mode.

Example

    python3 client.py --server http://chess.grantnet.us --username obuser --password obpass --threads 32 --nsockets 2 --fleet

To close the client, you may chose one of the following options:
1. Issue a SIGINT via CTRL-C on the terminal window
2. Create a file 'openbench.exit' in the same folder as client.py (useful for unattended/background runs)
