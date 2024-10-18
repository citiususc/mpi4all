import argparse
import os.path
import logging
import sys
import json

from mpi4all.parser import Parser
from mpi4all.generator.go import GoGenerator
from mpi4all.generator.java import JavaGenerator
from mpi4all.version import __version__


def parse_args():
    cli = argparse.ArgumentParser(prog='mpi4all',
                                  description='Universal Binding Generation for MPI Parallel Programming')

    cli.add_argument('--out', '-o', dest='out', action='store', metavar='path',
                     help='Place output in folder, by default is working directory', default=os.getcwd())
    cli.add_argument('--log', dest='log', action='store', metavar='lvl', choices=['info', 'warn', 'error'],
                     default='error', help='Log level, default error')

    parser = cli.add_argument_group('Parser Arguments')
    parser.add_argument('--cc', dest='cc', action='store', metavar='path',
                        help='MPI C compiler, by default search in PATH')
    parser.add_argument('--cxx', dest='cxx', action='store', metavar='path', default=None,
                        help='MPI C++ compiler, by default search in PATH')
    parser.add_argument('--exclude', dest='exclude', action='store', metavar='str', nargs='+', default=[],
                        help='Exclude functions and macros that match with any pattern')
    parser.add_argument('--enable-fortran', dest='fortran', action='store_true', default=False,
                        help='Parse MPI Fortran functions, which are disabled by default, to avoid linking errors '
                             'if they are not available')
    parser.add_argument('--dump', dest='dump', action='store', metavar='path', default=None,
                        help='Save blueprint as json file, - for stdout')
    parser.add_argument('--load', dest='load', action='store', metavar='path', default=None,
                        help='Disable parser and load a blueprint, - for stdin')
    parser.add_argument('--cache', dest='cache', action='store', metavar='path', default=None,
                        help='Make --dump if the blueprint does not exist and --load otherwise')

    go_gen = cli.add_argument_group('Go Generator Arguments')
    go_gen.add_argument('--go', dest='go', action='store_true',
                        help='Enable Go Generator')
    go_gen.add_argument('--no-generic', dest='go_generic', action='store_false', default=True,
                        help='Disable utility functions that require go 1.18+')
    go_gen.add_argument('--go-package', dest='go_package', action='store', metavar='name', default='mpi',
                        help='Go package name, default mpi')
    go_gen.add_argument('--go-out', dest='go_out', action='store', metavar='name', default=None,
                        help='Go output directory, by default <out>')

    java_gen = cli.add_argument_group('Java Generator Arguments')
    java_gen.add_argument('--java', dest='java', action='store_true',
                          help='Enable Java Generator')
    java_gen.add_argument('--jdk21', dest='jdk21', action='store_true',
                          help='Use JDK 21 preview instead of Java 22+ Generator')
    java_gen.add_argument('--java-package', dest='java_package', action='store', metavar='name',
                          help='Java package name, default org.mpi', default='org.mpi')
    java_gen.add_argument('--java-class', dest='java_class', action='store', metavar='name',
                          help='Java class name, default Mpi', default='Mpi')
    java_gen.add_argument('--java-out', dest='java_out', action='store', metavar='name', default=None,
                          help='Java output directory, default <out>')
    java_gen.add_argument('--java-lib-name', dest='java_lib_name', action='store', metavar='name',
                          help='Java native library name without any extension, default mpi4all',
                          default='mpi4all')
    java_gen.add_argument('--java-lib-out', dest='java_lib_out', action='store', metavar='name',
                          help='Java output directory for C library, default <java-out>/<java-lib-name>',
                          default=None)

    cli.add_argument("--version", action='version', version=__version__)

    args = cli.parse_args(['-h'] if len(sys.argv) == 1 else None)

    return args


def main():
    args = parse_args()
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
            mpi_info = Parser(
                cc=args.cc,
                cxx=args.cxx,
                exclude_list=args.exclude
            ).parse()

        if args.dump:
            if args.dump == '-':
                json.dump(mpi_info, sys.stdout, indent=4)
            else:
                with open(args.dump, mode='w') as file:
                    json.dump(mpi_info, file, indent=4)

        if args.go:
            logging.info("Generating Go bindings")
            GoGenerator(
                package=args.go_package,
                generic=args.go_generic,
                out=args.go_out if args.go_out else args.out,
            ).build(mpi_info)
            logging.info("Go bindings Ready")

        if args.java:
            logging.info("Generating Java bindings")
            java_out = args.java_out if args.java_out else args.out
            JavaGenerator(
                class_name=args.java_class,
                package=args.java_package,
                out=java_out,
                lib_name=args.java_lib_name,
                lib_out=args.java_lib_out if args.java_lib_out else java_out,
                jdk21=args.jdk21,
            ).build(mpi_info)
            logging.info("Java bindings Ready")

    except KeyboardInterrupt:
        print("\nAborted")
        exit(-1)
    except Exception as ex:
        print(str(type(ex).__name__) + ":  " + str(ex), file=sys.stderr)
        if args.log.upper() == 'INFO':
            raise ex
        exit(-1)


if __name__ == "__main__":
    main()
