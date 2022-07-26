#!/bin/bash

apt update
apt install -y gcc ssh gfortran

mkdir /test
cp -R /mpi/* /test
cp -R /test/include/* /usr/include
cp -R /test/lib/* /usr/lib

cp -R /src/* /test/go
cd /test/go
go build 
./mpitest
