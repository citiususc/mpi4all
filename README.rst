==========================================
MPI4All: A script to generate mpi bindings
==========================================

--------
Overview
--------

This package provides a Python script to parse and generate bindings for *Message Passing
Interface* (`MPI <https://www.mpi-forum.org/>`_) standard. The parser analyzes the MPI headers and generates a specification file with the defined macros, functions and types. The specification file is different for each version and implementation of MPI, the file can be stored to generate binding without using the parser.

We can currently generate bindings for Java and Go. Java makes use of Foreign Linker API and Foreign Memory Access API so the performance is significantly better than Java Native Interface (JNI) implementations. Go use cgo, so MPI headers are needed to compile. More languages may be added in the future, feel free to make a pull request.

The objective of the project is to create efficient bindings for MPI automatically. The project will never become an object oriented interface like `mpi4py <https://github.com/mpi4py/mpi4py/>`_, although an equivalent library could be built using our bindings.


MPI4All has been built in the field of the `IgnisHPC <https://github.com/ignishpc/>`_ project for  MPI usage.

-------
Install
-------

You can install MPI4All using pip::

 $ pip install mpi4all

------------
Dependencies
------------

* `Python <https://www.python.org/>`_ 3.8+ 
  and `PyPy <https://www.pypy.org/>`_.

* An MPI implementation, Java requires building shared/dynamic
  libraries.

Tested with:

* `MPICH <https://www.mpich.org/>`_: 3.1.4, 3.2.1, 3.3.2, 3.4.3, 4.0, 4.1a1

* `Open MPI <https://www.open-mpi.org/>`_: 4.0.7, 4.1.4, 5.0.0rc7

--------
Examples
--------


MPI4All
^^^^^^^

MPI4All can generate the bindings for **Java** and **Go** with the default MPI library installed in the system::

 $ mpi4all --go --java



Java
^^^^

External functions cannot use data inside java heap. The example shows how to use ``ByteBuffer.allocateDirect`` and ``MemorySession`` to allocate memory outside the java heap.

.. code-block:: java

    import org.mpi.Mpi;

    import java.lang.foreign.*;
    import java.nio.ByteBuffer;
    import java.nio.IntBuffer;

    public class Main {


        public static void main(String[] args) throws Throwable {
            Mpi.MPI_Init(Mpi.C_pointer.NULL.cast(), Mpi.MPI_ARGVS_NULL);

            int rank;
            int size;

            IntBuffer buffer = ByteBuffer.allocateDirect(4).asIntBuffer();

            Mpi.MPI_Comm_rank(Mpi.MPI_COMM_WORLD, new Mpi.C_pointer<>(MemorySegment.ofBuffer(buffer)));
            rank = buffer.get(0);
            try (MemorySession s = MemorySession.openConfined()) {
                Mpi.C_int c_size = Mpi.C_int.alloc(s);
                Mpi.MPI_Comm_size(Mpi.MPI_COMM_WORLD, c_size.pointer(s));
                size = c_size.get();
            }

            buffer = ByteBuffer.allocateDirect(4 * size).asIntBuffer();
            try (MemorySession s = MemorySession.openConfined()) {
                Mpi.C_int c_rank = Mpi.C_int.alloc(s);
                c_rank.set(rank);
                Mpi.MPI_Allgather(c_rank.pointer(s).cast(), 1, Mpi.MPI_INT,
                        new Mpi.C_pointer<>(MemorySegment.ofBuffer(buffer)), size, Mpi.MPI_INT, Mpi.MPI_COMM_WORLD);
            }

            for (int i = 0; i < size; i++) {
                if (i != buffer.get(i)) {
                    throw new RuntimeException("Allgather error");
                }
            }


            Mpi.MPI_Finalize();
        }
    }


GO
^^

``C_int`` and ``int`` data types are usually aliases but it is preferable to use ``C_int`` to avoid surprises. Functions with ``void *`` arguments use ``usafe.pointer`` instead, you can use the auxiliary functions ``mpi.P`` and ``mpi.PA`` to convert variables and array respectively to ``usafe.pointer``. All other pointers are converted to their equivalents in Go, ``&var`` or ``&array[0]`` is sufficient to send the memory address.

.. code-block:: go

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

    A script to generate mpi bindings

    optional arguments:
      -h, --help            show this help message and exit
      --out path            output folder, by default is working directory
      --log lvl             log level, default error
      --version             show program's version number and exit

    Mpi parser arguments:
      --gcc path            path of gcc binary, by default use the gcc in PATH
      --g++ path            path of g++ binary, by default use the g++ in PATH
      --mpi path            force a directory to search for mpi.h
      --exclude str [str ...]
                            exclude functions and macros that match with any
                            pattern
      --enable-fortran      enable mpi fortran functions disabled by default to
                            avoid linking errors, if they are not available
      --no-arg-names        use xi as param name in mpi functions
      --dump path           dump parser output, - for stdout
      --load path           ignore parser and load info from a dump file, - for
                            stdin
      --cache path          make --dump if the file does not exist and --load
                            otherwise

    Go builder arguments:
      --go                  enable Go generator
      --no-generic          Disable utility functions that require go 1.18+
      --go-package name     Go package name, default mpi
      --go-out name         Go output directory, by default <out>

    Java builder arguments:
      --java                enable Java (19+) generator
      --java-package name   Java package name, default org.mpi
      --java-class name     Java class name, default Mpi
      --java-out name       Java output directory, default <out>
      --java-lib-name name  Java C library name without any extension, default
                            mpi4alljava
      --java-lib-out name   Java output directory for C library, default <java-
                            out>/<java-lib-name>
