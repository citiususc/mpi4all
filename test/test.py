import subprocess
import sys
import os

TEST_D = os.path.abspath(os.getcwd())
WD = os.path.join(TEST_D, 'result')
MPICH_VERSIONS = ['3.2.1', '3.3.2', '3.4.3', '4.0', '4.1.3', '4.2.3']
OMPI_VERSIONS = ['4.0.7', '4.1.4', '5.0.5']


def test(name, f):
    print(name, file=sys.stderr, end='... ')
    try:
        f()
        print('OK', file=sys.stderr)
    except Exception as ex:
        print('FAIL', file=sys.stderr)
        print(ex, file=sys.stderr)
        exit(-1)


def log(msg):
    print(msg, file=sys.stderr, end='')


def cmd(args):
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True, input='')
    except subprocess.CalledProcessError as ex:
        raise RuntimeError(ex.stdout + ex.stderr)


def docker():
    cmd(['docker', '--version'])


def build():
    cmd(['docker', 'build', '-t', 'mpi4all', '..'])


def build_mpich(name, v):
    path = os.path.join(WD, name)
    cmd(['docker', 'build', '--build-arg', 'MPICH_VERSION=' + v, '--build-arg', 'MPICH_PATH=/mpi', '-t',
         name, 'mpich'])
    os.makedirs(path, exist_ok=True)
    cmd(['docker', 'run', '--rm', '-v', path + ':/mpi', name])


def build_ompi(name, v):
    path = os.path.join(WD, name)
    cmd(['docker', 'build', '--build-arg', 'OMPI_VERSION=' + v, '--build-arg', 'OMPI_PATH=/mpi', '-t',
         name, 'ompi'])
    os.makedirs(path, exist_ok=True)
    cmd(['docker', 'run', '--rm', '-v', path + ':/mpi', name])


def parser(path):
    cmd(['docker', 'run', '--rm', '-v', path + ':/mpi', 'mpi4all',
         '--cc', 'gcc -I /mpi/include',
         '--cxx', 'g++ -I /mpi/include', '--dump', '/mpi/f.json'])


def go_generator(path):
    cmd(['docker', 'run', '--rm', '-v', path + ':/mpi', 'mpi4all', '--load', '/mpi/f.json', '--out', '/mpi/go',
         '--go'])


def go_test(path):
    go = os.path.join(TEST_D, 'go')
    cmd(['docker', 'run', '--rm', '-v', path + ':/mpi', '-v', go + ':/src', 'golang:1.22-bookworm', '/src/test.sh'])


def java21_generator(path):
    cmd(['docker', 'run', '--rm', '-v', path + ':/mpi', 'mpi4all', '--load', '/mpi/f.json', '--out', '/mpi/java21',
         '--jdk21','--java'])


def java21_test(path):
    java = os.path.join(TEST_D, 'java')
    cmd(['docker', 'run', '--rm', '-v', path + ':/mpi', '-v', java + ':/java', 'eclipse-temurin:21-jdk-jammy',
         '/java/test21.sh'])

def java_generator(path):
    cmd(['docker', 'run', '--rm', '-v', path + ':/mpi', 'mpi4all', '--load', '/mpi/f.json', '--out', '/mpi/java',
         '--java'])


def java_test(path):
    java = os.path.join(TEST_D, 'java')
    cmd(['docker', 'run', '--rm', '-v', path + ':/mpi', '-v', java + ':/java', 'eclipse-temurin:23-jdk-noble',
         '/java/test.sh'])


def common_tests(name, path):
    test(name + ' parser', lambda: parser(path))
    test(name + ' go generator', lambda: go_generator(path))
    test(name + ' go build and test', lambda: go_test(path))
    test(name + ' java21 generator', lambda: java21_generator(path))
    test(name + ' java21 build and test', lambda: java21_test(path))
    test(name + ' java generator', lambda: java_generator(path))
    test(name + ' java build and test', lambda: java_test(path))


if __name__ == '__main__':
    os.makedirs(WD, exist_ok=True)
    test('docker', docker)
    test('mpi4all build', build)
    for v in MPICH_VERSIONS:
        name = 'mpich-' + v
        path = os.path.join(WD, name)
        if not os.path.exists(path):
            test(name + ' build', lambda: build_mpich(name, v))
        common_tests(name, path)

    for v in OMPI_VERSIONS:
        name = 'ompi-' + v
        path = os.path.join(WD, name)
        if not os.path.exists(path):
            test(name + ' build', lambda: build_ompi(name, v))
        common_tests(name, path)
