#!/bin/sh

rm db.sqlite3
rm -r OpenBench/migrations/*
rm -r OpenBench/__pycache__/*
rm -r OpenSite/__pycache__/*

python3 manage.py makemigrations
python3 manage.py migrate
python3 manage.py migrate --run-syncdb

winpty python3 manage.py createsuperuser