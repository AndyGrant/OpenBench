IMAGE := openbench-client

# Credentials/server are read from the environment (OPENBENCH_USERNAME, OPENBENCH_PASSWORD, OPENBENCH_SERVER)
# by manage.py -- export them, or source a local .env file, before spawning.

.PHONY: build spawn kill enter list plan

# Build the Docker image
build:
	docker build -t $(IMAGE) -f Dockerfile .

# Preview how spawn would carve up this machine's cores, without starting anything.
# e.g.: make plan THREADS=4 COUNT=8
plan:
	@if [ -z "$(THREADS)" ] || [ -z "$(COUNT)" ]; then \
		echo "usage: make plan THREADS=<n> COUNT=<n>"; exit 1; \
	fi
	python3 manage.py plan --threads $(THREADS) --count $(COUNT)

# Spawn COUNT pinned workers of THREADS logical threads each.
# CREDS is optional: a dir of credentials.<engine> files, bind-mounted read-only.
# e.g.: make spawn THREADS=32 COUNT=8 PREFIX=gpu101 [CREDS=/path/to/credentials-dir]
spawn: build
	@if [ -z "$(THREADS)" ] || [ -z "$(COUNT)" ] || [ -z "$(PREFIX)" ]; then \
		echo "usage: make spawn THREADS=<n> COUNT=<n> PREFIX=<host-prefix> [CREDS=<path-to-credentials-dir>]"; exit 1; \
	fi
	python3 manage.py spawn --threads $(THREADS) --count $(COUNT) --prefix $(PREFIX) $(if $(CREDS),--creds $(CREDS))

# Kill/remove all worker containers created from the image.
kill:
	python3 manage.py kill

# Show status of all worker containers
list:
	python3 manage.py list

# Open a shell in a running worker, e.g.: make enter WORKER=A
enter:
	@if [ -z "$(WORKER)" ]; then echo "usage: make enter WORKER=<label>"; exit 1; fi
	docker exec -it $(IMAGE)-$(WORKER) /bin/bash
