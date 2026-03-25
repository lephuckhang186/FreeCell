FROM mcr.microsoft.com/devcontainers/cpp:1-ubuntu-22.04

# Cài đặt GCC 12 (hỗ trợ C++23)
RUN apt-get update && apt-get install -y g++-12 \
    && update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-12 100

# Cài đặt thêm tools
RUN apt-get install -y cmake ninja-build