#!/bin/bash

apt update
apt install -y make gcc ssh gfortran

mkdir /test
cp -R /mpi/* /test
cp -R /test/include/* /usr/include
cp -R /test/lib/* /usr/lib

cp -R /java/* /test/java

find /test -name '*.java' >  /test/java/sources

javac --enable-preview --release 21 @/test/java/sources
cd /test/java/mpi4alljava
make
cp *.so /usr/lib/

java --enable-preview -cp /test/java org.main.Main
