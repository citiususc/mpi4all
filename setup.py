import setuptools
import mpi4all.version as version

with open("README.rst", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name='MPI4All',
    version=version.__version__,
    author="cesarpomar",
    author_email="cesaralfredo.pineiro@usc.es",
    description='MPI4All: A script to generate mpi binding',
    long_description=long_description,
    url="https://github.com/citiususc/mpi4all",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux ",
    ],
    entry_points={
        'console_scripts': ['mpi4all=mpi4all.main:main'],
    }
)
