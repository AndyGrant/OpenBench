#!/bin/bash

set -e

echo "Creating Conda environment..."
conda create --name py-ob python=3.10 -y

echo "Activating environment..."
source activate py-ob

echo "Installing requirements.txt..."
pip3 install -r requirements.txt

echo "Starting Django server..."
python3 manage.py runserver

echo "Server is running"
