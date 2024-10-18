#!/bin/bash

apt update
apt install -y gcc ssh gfortran

mkdir /test
cp -R /mpi/go /test
cp -R /mpi/include/* /usr/include
cp -R /mpi/lib/* /usr/lib

cp -R /src/* /test/go
cd /test/go
go build 
./mpitest
