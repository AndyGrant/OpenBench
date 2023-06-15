FROM python:3.12.0b2-alpine3.18

# Install git
RUN apk add --no-cache git

# Create a directory for the app
WORKDIR /

# Clone the repo
RUN git clone https://github.com/JouanDeag/OpenBench.git

# Install dependencies
WORKDIR /OpenBench

RUN pip3 install -r requirements.txt

# If the DB already exists, copy it
COPY db.sqlite3 /db.sqlite3
# Else initialize it
RUN python3 manage.py makemigrations
RUN python3 manage.py migrate

# Set initial env vars
ENV SECRET_KEY "MySecretKey"
ENV DEBUG True
ENV ALLOWED_HOSTS ['*']
ENV TIME_ZONE "UTC"

CMD [ "python3", "manage.py", "runserver", "0.0.0.0:8000" ]

EXPOSE 8000