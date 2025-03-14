==================================================================
MPI4All: Universal Binding Generation for MPI Parallel Programming
==================================================================

--------
Overview
--------

This package provides a Python script to parse and generate bindings for the *Message Passing
Interface* (`MPI <https://www.mpi-forum.org/>`_) standard. The parser analyzes the MPI headers and generates a specification file with the defined macros, functions and types. The specification file is different for each version and implementation of MPI, which can be stored to generate bindings without using the parser.

As case studies, we can currently generate bindings for Java and Go. Java makes use of Foreign Linker API and Foreign Memory Access API so the performance is significantly better than Java Native Interface (JNI) implementations. Go use cgo, so MPI headers are needed to compile. More languages may be added in the future, so feel free to make a pull request.

The goal of the project is to create efficient bindings for MPI automatically. The project will never become an object oriented interface like `mpi4py <https://github.com/mpi4py/mpi4py/>`_, although an equivalent library could be built using our bindings.


MPI4All has been built in the field of the `IgnisHPC <https://github.com/ignishpc/>`_ project for MPI usage.

I you use MPI4All, please cite:

- César Piñeiro, Álvaro Vázquez and Juan C. Pichel. `Towards Universal MPI Bindings for Enhanced New Language Support <https://doi.org/10.1016/j.jocs.2025.102557>`_. Journal of Computational Science, 2025.

- César Piñeiro, Álvaro Vázquez and Juan C. Pichel. `MPI4All: Universal Binding Generation for MPI Parallel Programming <https://doi.org/10.1007/978-3-031-63749-0_14>`_. 24th Int. Conference on Computational Science (ICCS). LNCS 14832, pp. 196–208, 2024.

-------
Install
-------

You can install MPI4All using pip::

 $ pip install mpi4all

------------
Dependencies
------------

* `Python <https://www.python.org/>`_ 3.9+

* An MPI Library

Tested with:

* `MPICH <https://www.mpich.org/>`_: 3.2.1, 3.3.2, 3.4.3, 4.0, 4.1.3, 4.2.3

* `Open MPI <https://www.open-mpi.org/>`_: 4.0.7, 4.1.4, 5.0.5

* `Intel MPI <https://www.intel.com/content/www/us/en/developer/tools/oneapi/mpi-library.html>`_: 2021.10.0

--------
Examples
--------


MPI4All
^^^^^^^

MPI4All can generate the bindings for **Java** and **Go** with the default MPI library installed in the system::

 $ mpi4all --go --java

or using a specification file::

 $ mpi4all --load mpich-4.0.json --go --java

Specification files can be generated with ``--dump`` or downloaded from the `releases <https://github.com/citiususc/mpi4all/releases>`_ section.

Java
^^^^

External functions cannot use data inside java heap. The example shows how to use ``ByteBuffer.allocateDirect`` and ``Arena`` to allocate memory outside the java heap.

.. code-block:: java

    import java.lang.foreign.*;
    import java.nio.ByteBuffer;
    import java.nio.IntBuffer;

    import org.mpi.Mpi;

    public class Main {
        public static void main(String[] args) throws Throwable {
            Mpi.MPI_Init(Mpi.C_pointer.NULL.cast(), Mpi.MPI_ARGVS_NULL);

            int rank;
            int size;

            // When the buffer is interpreted by the MPI function, the native order must be used.
            // If the MPI function only sends or receives the buffer, the order is indifferent.
            ByteBuffer buffer = ByteBuffer.allocateDirect(Mpi.C_int.byteSize()).order(ByteOrder.nativeOrder());

            Mpi.MPI_Comm_rank(Mpi.MPI_COMM_WORLD, new Mpi.C_pointer<>(MemorySegment.ofBuffer(buffer)));
            rank = buffer.get(0);
            try (Arena arena = Arena.ofConfined()) {// Using confined arena
                Mpi.C_int c_size = Mpi.C_int.alloc(arena);
                Mpi.MPI_Comm_size(Mpi.MPI_COMM_WORLD, c_size.pointer(arena));
                size = c_size.get();
            }

            buffer = ByteBuffer.allocateDirect(Mpi.C_int.byteSize() * size);

            Mpi.C_int c_rank = new Mpi.C_int(0); // Using auto gc arena
            Mpi.MPI_Allgather(c_rank.pointer().cast(), 1, Mpi.MPI_INT,
                    new Mpi.C_pointer<>(MemorySegment.ofBuffer(buffer)), 1, Mpi.MPI_INT, Mpi.MPI_COMM_WORLD);


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

.. code-block::

    usage: mpi4all [-h] [--out path] [--log lvl] [--cc path] [--cxx path]
                   [--exclude str [str ...]] [--enable-fortran] [--dump path]
                   [--load path] [--cache path] [--go] [--go-no-generic]
                   [--go-package name] [--go-out name] [--java] [--jdk21]
                   [--java-package name] [--java-class name] [--java-out name]
                   [--java-lib-name name] [--java-lib-out name] [--version]

    Universal Binding Generation for MPI Parallel Programming

    options:
      -h, --help            show this help message and exit
      --out path, -o path   Place output in folder, by default is working
                            directory
      --log lvl             Log level, default error
      --version             show program's version number and exit

    Parser Arguments:
      --cc path             MPI C compiler, by default search in PATH
      --cxx path            MPI C++ compiler, by default search in PATH
      --exclude str [str ...]
                            Exclude functions and macros that match with any
                            pattern
      --enable-fortran      Parse MPI Fortran functions, which are disabled by
                            default, to avoid linking errors if they are not
                            available
      --dump path           Save blueprint as json file, - for stdout
      --load path           Disable parser and load a blueprint, - for stdin
      --cache path          Make --dump if the blueprint does not exist and --load
                            otherwise

    Go Generator Arguments:
      --go                  Enable Go Generator
      --go-no-generic       Disable utility functions that require go 1.18+
      --go-package name     Go package name, default mpi
      --go-out name         Go output directory, by default <out>

    Java Generator Arguments:
      --java                Enable Java Generator
      --jdk21               Use JDK 21 preview instead of Java 22+ Generator
      --java-package name   Java package name, default org.mpi
      --java-class name     Java class name, default Mpi
      --java-out name       Java output directory, default <out>
      --java-lib-name name  Java native library name without any extension,
                            default mpi4all
      --java-lib-out name   Java output directory for C library, default <java-
                            out>/<java-lib-name>

