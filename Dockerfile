FROM ubuntu:22.04

#ENV LLVM_VERSION=16
ARG DEBIAN_FRONTEND=noninteractive

# install some useful tools and dependencies
RUN apt-get -u update \
    && apt-get -qq upgrade \
    # Setup Kitware repo for the latest cmake available:
    && apt-get -qq install \
        apt-transport-https ca-certificates gnupg software-properties-common wget apt-utils \
    && wget -O - https://apt.kitware.com/keys/kitware-archive-latest.asc 2>/dev/null \
        | gpg --dearmor - \
        | tee /etc/apt/trusted.gpg.d/kitware.gpg >/dev/null \
    && apt-add-repository 'deb https://apt.kitware.com/ubuntu/ jammy main' \
    && apt-get -u update \
    && apt-get -qq upgrade \
    && apt-get -qqy install cmake \
        ca-certificates \
        build-essential \
        python3 \
        ninja-build \
        ccache \
        xz-utils \
        curl \
        git \
        bzip2 \
        lzma \
        xz-utils \
        lsb-release \
        wget \
        software-properties-common \
        libboost-all-dev \
        libopenblas-dev

# install LLVM with RV
RUN git clone https://github.com/llvm/llvm-project.git; cd llvm-project/llvm; git checkout 7cbf1a259152; git submodule update --init --recursive; git clone https://github.com/moritz-2001/RV.git rv; cd rv; git submodule update --init --recursive; cd ..; \
    mkdir build; cd build;  \
    cmake -DCMAKE_C_COMPILER=`which gcc` -DCMAKE_CXX_COMPILER=`which g++` -DCMAKE_BUILD_TYPE=Release -DLLVM_ENABLE_ASSERTIONS=ON -DLLVM_ENABLE_PROJECTS="clang;compiler-rt;lld;openmp" -DOPENMP_ENABLE_LIBOMPTARGET=OFF -DLLVM_TARGETS_TO_BUILD="AMDGPU;NVPTX;X86" -DCLANG_ANALYZER_ENABLE_Z3_SOLVER=0 -DLLVM_INCLUDE_BENCHMARKS=0 -DLLVM_INCLUDE_EXAMPLES=0 -DLLVM_INCLUDE_TESTS=0 -DCMAKE_INSTALL_RPATH_USE_LINK_PATH=ON -DCMAKE_INSTALL_RPATH=lib -DLLVM_ENABLE_OCAMLDOC=OFF -DLLVM_ENABLE_BINDINGS=OFF -DLLVM_TEMPORARILY_ALLOW_OLD_TOOLCHAIN=OFF -DLLVM_BUILD_LLVM_DYLIB=ON -DLLVM_ENABLE_DUMP=OFF  ../ -DLLVM_EXTERNAL_PROJECTS="rv" -DLLVM_EXTERNAL_RV_SOURCE_DIR=../rv -G Ninja -DLLVM_ENABLE_RTTI=ON; \
    ninja install; cd /; rm -rf llvm-project


## install ethminer dependencies: ethash, json, boost
RUN mkdir downloads; \
  cd /downloads; wget https://github.com/chfast/ethash/archive/refs/tags/v0.4.3.tar.gz; tar -xvf v0.4.3.tar.gz; cd ethash-0.4.3; mkdir build; cd build; cmake -DETHASH_BUILD_TESTS=OFF ..; make -j`nproc`; make install -j \
  cd /dowloads; wget https://github.com/open-source-parsers/jsoncpp/archive/refs/tags/1.9.5.tar.gz; tar -xvf 1.9.5.tar.gz; cd jsoncpp-1.9.5; mkdir build; cd build; cmake ..; make -j`nproc`; make install -j \
  cd /downloads; wget https://archives.boost.io/release/1.82.0/source/boost_1_82_0.tar.gz; tar -xvf boost_1_82_0.tar.gz; cd boost_1_82_0; ./bootstrap.sh; ./b2 -j`nproc`; ./b2 install -j`nproc` \
  cd /downloads; wget https://github.com/openssl/openssl/releases/download/OpenSSL_1_1_1f/openssl-1.1.1f.tar.gz; tar -xvf openssl-1.1.1f.tar.gz; cd openssl-1.1.1f; ./config shared zlib; make -j`nproc`; make install -j; \
  rm -rf /downloads

COPY ./main.py main.py

CMD python3 main.py
