FROM python:3.12

# Copy requirements.txt to the image
COPY requirements.txt /app/requirements.txt

# Set the working directory
WORKDIR /app

# Install dependencies
RUN pip install -r requirements.txt

# Copy the rest of your application files
COPY . /app

# Set the command to run your application
CMD ["python", "./Client/client.py"]