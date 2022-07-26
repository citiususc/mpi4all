
FROM debian:buster-slim

ARG MPICH_VERSION=3.4.3
ARG MPICH_PATH=/usr

RUN apt update && \
	apt install -y gcc g++ gfortran wget tar make python3

ENV CH4_V 3.3
RUN	mkdir /mpich && \
	cd /mpich && \
	wget https://www.mpich.org/static/downloads/${MPICH_VERSION}/mpich-${MPICH_VERSION}.tar.gz && \
	tar -zxf mpich-${MPICH_VERSION}.tar.gz && \
	cd mpich-${MPICH_VERSION} && \
    if [ "$(printf '%s\n' ${MPICH_VERSION} ${CH4_V} | sort -V | head -n1)" = "${CH4_V}" ]; then \
        ./configure --prefix ${MPICH_PATH} --with-device=ch4:ofi --with-libfabric=embedded; \
    else \
        ./configure --prefix ${MPICH_PATH}; \
    fi && \
	make -j
	
WORKDIR /mpich/mpich-${MPICH_VERSION}
ENTRYPOINT  make install