package org.main;

import java.lang.foreign.*;
import java.nio.ByteBuffer;
import java.nio.IntBuffer;

import org.mpi.Mpi;

public class Main {
    public static void main(String[] args) throws Throwable {
        Mpi.MPI_Init(Mpi.C_pointer.NULL.cast(), Mpi.MPI_ARGVS_NULL);

        int rank;
        int size;

        IntBuffer buffer = ByteBuffer.allocateDirect(Mpi.C_int.byteSize()).asIntBuffer();

        Mpi.MPI_Comm_rank(Mpi.MPI_COMM_WORLD, new Mpi.C_pointer<>(MemorySegment.ofBuffer(buffer)));
        rank = buffer.get(0);
        try (Arena arena = Arena.ofConfined()) {// Using confined arena
            Mpi.C_int c_size = Mpi.C_int.alloc(arena);
            Mpi.MPI_Comm_size(Mpi.MPI_COMM_WORLD, c_size.pointer(arena));
            size = c_size.get();
        }

        buffer = ByteBuffer.allocateDirect(Mpi.C_int.byteSize() * size).asIntBuffer();

        Mpi.C_int c_rank = Mpi.C_int.alloc(); // Using auto gc arena
        c_rank.set(rank);
        Mpi.MPI_Allgather(c_rank.pointer().cast(), 1, Mpi.MPI_INT,
                new Mpi.C_pointer<>(MemorySegment.ofBuffer(buffer)), size, Mpi.MPI_INT, Mpi.MPI_COMM_WORLD);


        for (int i = 0; i < size; i++) {
            if (i != buffer.get(i)) {
                throw new RuntimeException("Allgather error");
            }
        }


        Mpi.MPI_Finalize();
    }
}