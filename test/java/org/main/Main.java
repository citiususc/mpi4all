package org.main;

import org.mpi.Mpi;

import java.lang.foreign.*;

public class Main {


    public static void main(String[] args) throws Throwable {
        Mpi.MPI_Init(Mpi.C_pointer.NULL.cast(), Mpi.MPI_ARGVS_NULL);

        int[] array = new int[]{1, 2, 3, 4, 5};
        int[] result = new int[array.length];

        try (MemorySession s = MemorySession.openConfined()) {
            Mpi.C_pointer<Mpi.C_int> tmp = Mpi.C_int.array(s, array.length);
            Mpi.MPI_Allgather(Mpi.C_pointer.from(s, MemorySegment.ofArray(array)), array.length, Mpi.MPI_INT,
                    tmp.cast(), array.length, Mpi.MPI_INT, Mpi.MPI_COMM_WORLD);
            tmp.to(MemorySegment.ofArray(result));
        }

        for (int i = 0; i < array.length; i++) {
            if (array[i] != result[i]) {
                throw new RuntimeException("Allgather error");
            }
        }

        Mpi.MPI_Finalize();
    }
}