import argparse
import os.path
import logging
import sys
import json

from mpi4all.mpiparser import MpiParser
from mpi4all.gobuilder import GoBuilder
from mpi4all.javabuilder import JavaBuilder
from mpi4all.version import __version__


def cli():
    parser = argparse.ArgumentParser(prog='mpi4all', description='A script to generate mpi bindings')
    parser.add_argument('--out', dest='out', action='store', metavar='path',
                        help='Output folder, by default is working directory', default='./')
    parser.add_argument('--log', dest='log', action='store', metavar='lvl', choices=['info', 'warn', 'error'],
                        default='error', help='Log level, default error')

    p_parser = parser.add_argument_group('Mpi parser arguments')
    p_parser.add_argument('--cc', dest='cc', action='store', metavar='path',
                          help='MPI C compiler, by default uses the \'mpicc\' in PATH', default="mpicc")
    p_parser.add_argument('--cxx', dest='cxx', action='store', metavar='path',
                          help='MPI C++ compiler, by default uses the \'mpic++\' in PATH', default='mpic++')
    p_parser.add_argument('--exclude', dest='exclude', action='store', metavar='str', nargs='+', default=[],
                          help='Exclude functions and macros that match with any pattern')
    p_parser.add_argument('--enable-fortran', dest='fortran', action='store_true',
                          help='Parse MPI Fortran functions, which are disabled by default, to avoid linking errors '
                               'if they are not available', default=False)
    p_parser.add_argument('--no-arg-names', dest='no_arg_names', action='store_true',
                          help='Use xi as the parameter name in MPI functions', default=False)
    p_parser.add_argument('--dump', dest='dump', action='store', metavar='path', default=None,
                          help='Dump parser output as json file, - for stdout')
    p_parser.add_argument('--load', dest='load', action='store', metavar='path', default=None,
                          help='Don\'t use a parser and load info from a JSON file, - for stdin')
    p_parser.add_argument('--cache', dest='cache', action='store', metavar='path', default=None,
                          help='Make --dump if the file does not exist and --load otherwise')

    go_parser = parser.add_argument_group('Go builder arguments')
    go_parser.add_argument('--go', dest='go', action='store_true',
                           help='Enable Go generator')
    go_parser.add_argument('--no-generic', dest='go_generic', action='store_false',
                           help='Disable utility functions that require go 1.18+', default=True)

    go_parser.add_argument('--go-package', dest='go_package', action='store', metavar='name',
                           help='Go package name, default mpi', default='mpi')
    go_parser.add_argument('--go-out', dest='go_out', action='store', metavar='name',
                           help='Go output directory, by default <out>', default=None)

    java_parser = parser.add_argument_group('Java builder arguments')
    java_parser.add_argument('--java', dest='java', action='store_true',
                             help='Enable Java 21 generator')
    java_parser.add_argument('--java-package', dest='java_package', action='store', metavar='name',
                             help='Java package name, default org.mpi', default='org.mpi')
    java_parser.add_argument('--java-class', dest='java_class', action='store', metavar='name',
                             help='Java class name, default Mpi', default='Mpi')
    java_parser.add_argument('--java-out', dest='java_out', action='store', metavar='name',
                             help='Java output directory, default <out>', default=None)
    java_parser.add_argument('--java-lib-name', dest='java_lib_name', action='store', metavar='name',
                             help='Java C library name without any extension, default mpi4alljava',
                             default='mpi4alljava')
    java_parser.add_argument('--java-lib-out', dest='java_lib_out', action='store', metavar='name',
                             help='Java output directory for C library, default <java-out>/<java-lib-name>',
                             default=None)

    parser.add_argument("--version", action='version', version=str(__version__))

    args = parser.parse_args(['-h'] if len(sys.argv) == 1 else None)

    return args


def main():
    args = cli()
    try:
        logging.basicConfig(level=args.log.upper(),
                            format='%(asctime)s <%(levelname)-s> [%(filename)-s:%(lineno)d] %(message)s',
                            datefmt='%B %e, %Y %I:%M:%S %p',
                            )
        if not args.fortran:
            args.exclude.extend(['_(c2)?f[0-9cf]*$', '_DEFINED', '_INCLUDED'])

        if args.cache:
            if os.path.exists(args.cache):
                args.load = args.cache
            else:
                args.dump = args.cache

        if args.load:
            if args.load == '-':
                mpi_info = json.load(sys.stdin)
            else:
                with open(args.load) as file:
                    mpi_info = json.load(file)
        else:
            mpi_info = MpiParser(
                cc=args.cc,
                cxx=args.cxx,
                exclude_list=args.exclude,
                get_func_args=not args.no_arg_names
            ).parse()

        if args.dump:
            if args.dump == '-':
                json.dump(mpi_info, sys.stdout, indent=4)
            else:
                with open(args.dump, mode='w') as file:
                    json.dump(mpi_info, file, indent=4)

        if args.go:
            logging.info("Generating Go source")
            GoBuilder(
                package=args.go_package,
                generic=args.go_generic,
                out=args.go_out if args.go_out else args.out,
            ).build(mpi_info)
            logging.info("Go source Ready")

        if args.java:
            logging.info("Generating Java source")
            JavaBuilder(
                class_name=args.java_class,
                package=args.java_package,
                out=args.java_out if args.java_out else args.out,
                lib_name=args.java_lib_name,
                lib_out=args.java_lib_out,
            ).build(mpi_info)
            logging.info("Java source Ready")

    except KeyboardInterrupt as ex:
        print("\nAborted")
        exit(-1)
    except Exception as ex:
        print(str(type(ex).__name__) + ":  " + str(ex), file=sys.stderr)
        if args.log.upper() == 'INFO':
            raise ex
        exit(-1)


if __name__ == "__main__":
    main()
