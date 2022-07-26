
FROM debian:buster-slim

ARG OMPI_VERSION=4.1.4
ARG OMPI_PATH=/usr

RUN apt update && \
	apt install -y gcc g++ gfortran wget tar make python3
	
RUN	mkdir /ompi && \
	cd /ompi && \
	wget https://download.open-mpi.org/release/open-mpi/v${OMPI_VERSION%.*}/openmpi-${OMPI_VERSION}.tar.gz && \
	tar -zxf openmpi-${OMPI_VERSION}.tar.gz && \
	cd openmpi-${OMPI_VERSION} && \
	./configure --prefix ${OMPI_PATH} && \
	make -j
	
WORKDIR /ompi/openmpi-${OMPI_VERSION}
ENTRYPOINT  make install


