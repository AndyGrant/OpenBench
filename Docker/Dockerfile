FROM ubuntu:24.04

# Install prerequisites (including gcc, g++, glibc, cmake, make, ninja, and python3)
# Latest available gcc and g++ are installed - should we be specific about the version?
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y \
    lsb-release \
    software-properties-common \
    gnupg \
    curl \
    git \
    build-essential \
    cmake \
    ninja-build \
    python3 \
    python3-pip \
    python3-venv \
    wget

# Install LLVM 20
RUN wget https://apt.llvm.org/llvm.sh && \
    chmod +x llvm.sh && \
    ./llvm.sh 20 && \
    rm -rf llvm.sh

RUN ln -s /usr/bin/clang-20 /usr/bin/clang && \
    ln -s /usr/bin/clang++-20 /usr/bin/clang++

ENV CC=clang
ENV CXX=clang++

# Install .NET Core SDK and Runtime - 9.0
RUN add-apt-repository ppa:dotnet/backports

RUN apt-get install -y \
    dotnet-sdk-9.0

# Install Rust (Latest stable version - should we be specific about the version?)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    --no-modify-path  \
    --default-toolchain stable \
    --no-self-update

ENV PATH="/root/.cargo/bin:$PATH"

# Install Zig 0.14.1
ENV ZIG_VERSION=0.14.1
ENV ZIG_HOME=/opt/zig

RUN curl -LO https://ziglang.org/download/${ZIG_VERSION}/zig-x86_64-linux-${ZIG_VERSION}.tar.xz && \
    tar -xf zig-x86_64-linux-${ZIG_VERSION}.tar.xz && \
    mv zig-x86_64-linux-${ZIG_VERSION} ${ZIG_HOME} && \
    ln -s ${ZIG_HOME}/zig /usr/bin/zig && \
    rm zig-x86_64-linux-${ZIG_VERSION}.tar.xz

# Clone the OpenBench Client
RUN git clone https://github.com/AndyGrant/OpenBench

# Fetch the OpenBench Client startup script
COPY run.sh /OpenBench/Client/run.sh

RUN python3 -m venv /.venv

ENV PATH="/.venv/bin:$PATH"

# Set the working directory to the OpenBench Client
WORKDIR /OpenBench/Client

# Install OpenBench Client dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Execute the OpenBench Client startup script
CMD ["bash", "run.sh"]