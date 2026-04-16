FROM alpine:3.21

RUN apk add --no-cache \
    build-base \
    flex \
    bison \
    openssl-dev \
    elfutils-dev \
    bc \
    wget \
    vim \
    xz \
    cpio \
    pahole \
    bash \
    perl \
    linux-headers \
    diffutils \
    findutils

WORKDIR /build

CMD ["bash"]
