#!/bin/bash

apt update
apt install -y make gcc ssh gfortran

mkdir /test
cp -R /mpi/java /test/java
cp -R /mpi/include/* /usr/include
cp -R /mpi/lib/* /usr/lib

cp -R /java/* /test/java

find /test -name '*.java' >  /test/java/sources

javac @/test/java/sources
cd /test/java/mpi4all
make
cp *.so /usr/lib/

java -cp /test/java org.main.Main
