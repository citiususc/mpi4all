package main

import "mpitest/mpi"

func main() {
	if err := mpi.MPI_Init(nil, nil); err != nil {
		panic(err)
	}

	array := []mpi.C_int{1, 2, 3, 4, 5}
	result := make([]mpi.C_int, len(array))

	if err := mpi.MPI_Allgather(mpi.PA(&array), mpi.C_int(len(array)), mpi.MPI_INT,
		mpi.PA(&result), mpi.C_int(len(result)), mpi.MPI_INT, mpi.MPI_COMM_WORLD); err != nil {
		panic(err)
	}

	for i := 0; i < len(array); i++ {
		if array[i] != result[i] {
			panic("Allgather error")
		}
	}

	if err := mpi.MPI_Finalize(); err != nil {
		panic(err)
	}

}