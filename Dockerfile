FROM python:3.10-slim-buster

RUN apt update && \
	apt -y install \
		gcc \
		g++ \
		make && \
	rm -rf /var/lib/apt/lists/* && \
	mkdir /tmp/mpi4all
	
COPY . /tmp/mpi4all

RUN cd /tmp/mpi4all && \
	python3 setup.py install && \
	rm -fR /tmp/mpi4all

RUN mpi4all -h

ENTRYPOINT ["/usr/local/bin/mpi4all"]
