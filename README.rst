==========================================
MPI4All: A script to generate mpi wrappers
==========================================

--------
Overview
--------



-------
Install
-------

You can install MPI4All using pip::

 $ pip install mpi4all



--------
Examples
--------


MPI4All
^^^^^^^

 $ mpi4all --go --java


Java
^^^^

.. code-block:: java


GO
^^

.. code-block::go

    package main

    import "mpi"

    func main() {
        if err := mpi.MPI_Init(nil, nil); err != nil {
            panic(err)
        }

        var rank mpi.C_int
        var size mpi.C_int

        if err := mpi.MPI_Comm_rank(mpi.MPI_COMM_WORLD, &rank); err != nil {
            panic(err)
        }

        if err := mpi.MPI_Comm_size(mpi.MPI_COMM_WORLD, &size); err != nil {
            panic(err)
        }

        result := make([]mpi.C_int, int(size))

        if err := mpi.MPI_Allgather(mpi.P(&rank), 1, mpi.MPI_INT,
            mpi.PA(&result), mpi.C_int(len(result)), mpi.MPI_INT, mpi.MPI_COMM_WORLD); err != nil {
            panic(err)
        }

        for i := 0; i < int(size); i++ {
            if i != int(result[i]) {
                panic("Allgather error")
            }
        }

        if err := mpi.MPI_Finalize(); err != nil {
            panic(err)
        }

    }
-----
Usage
-----

.. code-block:: shell

    usage: mpi4all [-h] [--out path] [--log lvl] [--gcc path] [--g++ path]
                   [--mpi path] [--exclude path [path ...]] [--enable-fortran]
                   [--no-arg-names] [--dump path] [--load path] [--cache path]
                   [--go] [--no-generic] [--go-package name] [--go-out name]
                   [--java] [--java-package name] [--java-class name]
                   [--java-out name] [--java-lib-name name] [--java-lib-out name]
                   [--version]

    A script to generate mpi wrappers

    optional arguments:
      -h, --help            show this help message and exit
      --out path            output folder, by default is working directory
      --log lvl             log level, default error
      --version             show program's version number and exit

    Mpi parser arguments:
      --gcc path            path of gcc binary, by default use the gcc in PATH
      --g++ path            path of g++ binary, by default use the g++ in PATH
      --mpi path            force a directory to search for mpi.h
      --exclude path [path ...]
                            exclude functions and macros that match with any
                            pattern
      --enable-fortran      enable mpi fortran functions disabled by default to
                            avoid linking errors if they are not available.
                            Default --exclude _f2c _c2f _f90
      --no-arg-names        use xi as param name in mpi functions
      --dump path           dump parser output, - for stdout
      --load path           ignore parser and load info from a dump file, - for
                            stdin
      --cache path          make --dump if the file does not exist and --load
                            otherwise

    Go builder arguments:
      --go                  enable Go generator
      --no-generic          Disable utility functions that require go 1.18+
      --go-package name     Go package name, default (mpi)
      --go-out name         Go output directory, by default <out>

    Java builder arguments:
      --java                enable Java (19+) generator
      --java-package name   Java package name, default org.mpi
      --java-class name     Java class name, default Mpi
      --java-out name       Java output directory, by default <out>
      --java-lib-name name  Java C library name without any extension, default
                            mpi4alljava
      --java-lib-out name   Java output directory for C library, by default <java-
                            out>/<java-lib-name>
