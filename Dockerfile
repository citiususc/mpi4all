FROM python:3.12.7-bookworm

RUN apt update && \
	apt -y install \
		gcc \
		g++ \
		make && \
	rm -rf /var/lib/apt/lists/* && \
	mkdir /tmp/mpi4all
	
COPY . /tmp/mpi4all

RUN cd /tmp/mpi4all && \
	python3 -m pip install . && \
	rm -fR /tmp/mpi4all

ENTRYPOINT ["/usr/local/bin/mpi4all"]
