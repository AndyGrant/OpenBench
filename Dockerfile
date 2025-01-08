FROM ubuntu:jammy

RUN apt-get update
RUN apt-get install git python3 pip curl make g++ gcc htop cargo git-lfs openjdk-17-jdk maven cmake clang lld -y

RUN git clone https://github.com/kelseyde/OpenBench.git /OpenBench
RUN cp -r /OpenBench/Client /app

COPY toolchains.xml /root/.m2/toolchains.xml

WORKDIR /app
ADD start.sh /app/
RUN chmod +x /app/start.sh

RUN pip3 install -r requirements.txt

# Define default environment variables
ENV OB_USER=dan
ENV OB_PASS=3KQoeEQCcCk3lHm
ENV OB_URL=http://kelseyde.pythonanywhere.com
ENV OB_THREADS=8

# Default command to run the OpenBench client
CMD ["sh", "-c", "/app/start.sh"]