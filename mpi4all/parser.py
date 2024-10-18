import os.path
import subprocess
import tempfile
import shutil
import platform
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Union, Any
from mpi4all.version import __version__
from functools import partial


def _find_compiler(*names: str) -> str:
    for name in names:
        if shutil.which(name) is not None:
            return name
    return names[0]


def _run(cmd: str, *args: str, text: str = '', check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([cmd] + list(args), check=check, capture_output=True, text=True, input=text)


_CXX_TEMPLATE_NAME = """
      #include <mpi.h>        
      #include "cxxabi.h"
      #include <iostream>

      int main(int argc, char *argv[]){{
          int status;
          char *name = abi::__cxa_demangle(typeid({name}).name(), 0, 0, &status);
          if (status == 0) {{
              std::cout << name << std::endl;
              free(name);
          }} else {{
              return -1;
          }}
          std::cout << sizeof({name}) <<std::endl;
          return 0;
      }}
"""


class Parser:
    CAST_RE = re.compile(r'^\(?\((MPI_\w+[ *]*)\)|OMPI_PREDEFINED_GLOBAL\([ ]*(MPI_\w+[ *]*)')

    def __init__(self, cc: str, cxx: str, exclude_list: List[str]):
        args_cc = cc.split() if cc is not None else [_find_compiler("mpicc", "mpiicc", "mpigcc")]
        args_cxx = cxx.split() if cxx is not None else [_find_compiler("mpicxx", "mpiicxx", "mpigxx", "mpic++")]

        self._cc = partial(_run, *args_cc)
        self._cxx = partial(_run, *args_cxx)
        self._exclude_patterns = list(map(lambda e: re.compile(e), exclude_list))
        self._types = dict()
        self._info = dict()

    def _is_excluded(self, s: str):
        for pattern in self._exclude_patterns:
            if pattern.search(s):
                return True
        return False

    def _c_info(self, name: str, wd: str) -> (str, bool, int, str):
        test_code = _CXX_TEMPLATE_NAME.format(name=name)
        test_bin = os.path.join(wd, name)

        try:
            self._cxx('-fpermissive', '-x', 'c++', '-o', test_bin, '-', text=test_code)
            typename, n_bytes = _run(test_bin).stdout.split('\n')[:2]
            os.remove(test_bin)

            if self._cxx('-shared', '-fPIC', '-include', 'mpi.h', '-o', '/dev/null', '-x', 'c++', '-',
                         check=False, text=f'auto x = {name};').returncode == 0:
                is_var = True
            else:
                is_var = False

            return typename, is_var, n_bytes, None
        except subprocess.CalledProcessError as ex:
            return None, None, None, ex.stderr

    def _macro_filter(self, lines: List[str]) -> List[str]:
        filtered_lines = list()
        for line in lines:
            if not line.startswith('#define MPI_'):
                if '_VERSION' in line:
                    name, value = line.split(' ', 2)[1:]
                    if 'MPICH_VERSION' in line and self._info.get('vendor', 'unknown') == 'unknown':
                        self._info['vendor'] = 'mpich'
                        self._info['version'] = value.replace('"', '')
                    elif 'OMPI_' in line and self._info.get('vendor', 'unknown') == 'unknown':
                        self._info['vendor'] = 'ompi'
                        if 'version' not in self._info:
                            self._info['version'] = '..'
                        if '_MAJOR_' in line:
                            self._info['version'] = value + self._info['version']
                        elif '_RELEASE_' in line:
                            self._info['version'] += value
                        elif '_MINOR_' in line:
                            self._info['version'] = self._info['version'].replace('..', value)
                    elif 'I_MPI_VERSION' in line:
                        self._info['vendor'] = 'impi'
                        self._info['version'] = value.replace('"', '')
                    elif 'vendor' not in self._info:
                        self._info['vendor'] = 'unknown'
                        self._info['version'] = ''
                    continue
            elif not self._is_excluded(line):
                filtered_lines.append(line)
        return filtered_lines

    def _parse_macro(self, line: str, wd: str) -> Union[Dict[str, str], None]:
        macro = line.split(' ', 1)[1]
        name = None
        value = None
        for i in range(len(macro)):
            if macro[:-i].isidentifier():
                name = macro[:-i]
                value = macro[len(name):].strip()
                break

        if name is None:
            return None

        r = {'raw': line, 'name': name, 'value': value}

        typename, var, bytes, error = self._c_info(name, wd)
        if error:
            r["error"] = error
            return r

        r['type'] = typename
        r['bytes'] = bytes
        r['var'] = var
        cast = Parser.CAST_RE.match(value)
        if cast:
            r['mtype'] = (cast.group(1) if cast.group(1) else cast.group(2)).strip()

        return r

    def _parse_macros(self, wd: str) -> List[Dict[str, str]]:
        logging.info('Macros dumped')
        macro_dump = self._cc('-dM', '-E', '-include', 'mpi.h', '-').stdout
        logging.info('Parsing macros')
        macro_lines = self._macro_filter(macro_dump.splitlines())
        with ThreadPoolExecutor() as pool:
            parsed_macros = pool.map(lambda l: self._parse_macro(l, wd), macro_lines)
        logging.info('Macros ready')
        filtered_macros = list()

        for m in parsed_macros:
            if m is None:
                continue
            if "error" in m:
                logging.warning(f'{m["raw"]} ignored: {m["error"]}')
            else:
                self._types[m['type']] = m['bytes']
                if '*' in m['type']:
                    self._types['*'] = m['bytes']
                del m['bytes']
                if 'mtype' in m:
                    self._types[m['mtype']] = m['type']
                    m['type'] = m['mtype']
                    del m['mtype']

                filtered_macros.append(m)

        return filtered_macros

    def _create_type(self, f: Dict[str, str], arg: str, wd: str):
        nc_arg = arg.replace('const', '').strip()
        if '*' in arg:
            self._types[arg] = self._types['*']
        elif nc_arg in self._types:
            self._types[arg] = self._types[nc_arg]
        else:
            typename, _, bytes, error = self._c_info(arg, wd)
            if error:
                f['error'] = error
                logging.error(f['name'] + error)
            self._types[arg] = typename
            self._types[typename] = bytes

    def _parse_funcs(self, wd: str):
        func_file = os.path.join(wd, 'func.X')
        self._cc('-x', 'c', '-shared', '-o', '/dev/null', '-aux-info', func_file, '-include', 'mpi.h', '-')

        with open(func_file) as file:
            func_dump = file.readlines()

        functions = list()
        for line in func_dump:
            f = {}
            try:
                header = line[min(line.index('*/') + 2, len(line)):].strip()
                if header.startswith('extern'):
                    header = header.replace('extern', '', 1)
            except ValueError:
                continue
            if not header:
                continue

            header = header.replace(';', '').strip()
            f['header'] = header

            rt, header = header.split(' ', 1)
            f['rtype'] = rt.strip()
            header = header.strip()

            fn, header = header.split('(', 1)
            f['name'] = fn.strip()
            header = header.strip()
            if not f['name'].startswith('MPI_') or self._is_excluded(f['name']):
                continue

            header = header[:-1].strip()
            f['args'] = list()
            for arg in header.split(','):
                arg = arg.strip()
                f['args'].append({'type': arg})
                if '...' in arg:
                    f['vargs'] = True
                elif arg not in self._types:
                    if arg == 'void':
                        continue
                    self._create_type(f, arg, wd)

            self._create_type(f, f['rtype'], wd)
            if len(f['args']) == 1 and f['args'][0]['type'] == 'void':
                f['args'].clear()

            if 'error' not in f:
                functions.append(f)

        name_info = self._cc('-E', '-include', 'mpi.h', '-').stdout
        for f in functions:
            try:
                if len(f['args']) == 0:
                    continue
                start = name_info.index(f['name'] + '(')
                start += len(f['name']) + 1
                end = name_info.index(';', start)
                header = name_info[start:end - 1].strip()
                values = header.split(',')
                for i, v in enumerate(values):
                    name = re.sub(r'[^a-zA-Z0-9_ ]', '', v).split(' ')[-1]
                    if not name:
                        name = 'x' + str(i)
                    f['args'][i]['name'] = name
            except Exception:
                logging.warning(f['name'] + ' param name not found')
                for i in range(len(f['args'])):
                    f['args'][i]['name'] = 'x' + str(i)


        return functions

    def _type_fix(self, result: Dict[str, Any]) -> Dict[str, Any]:
        for tp, val in list(result['types'].items()):
            if tp.startswith('MPI') and val.endswith('_t*'):
                del result['types'][val]
                result['types'][tp] = result['types']['*']

                for m in result['macros']:
                    if val in m['type']:
                        m['type'] = m['type'].replace(val, tp)

                for f in result['functions']:
                    if val in f['rtype']:
                        f['rtype'] = f['rtype'].replace(val, tp)
                    for arg in f['args']:
                        if val in arg['type']:
                            arg['type'] = arg['type'].replace(val, tp)

                for tp2, val2 in list(result['types'].items()):
                    if val in val2 and not val2.endswith('_t*'):
                        result['types'][tp2] = result['types'][tp2].replace(val, tp)
                    if val in tp2 and not tp2.endswith('_t*'):
                        result['types'][tp2.replace(val, tp)] = result['types'][tp2]

        for tp, val in result['types'].items():
            if '(' in tp and val == '1':
                result['types'][tp] = result['types']['*']

        return result

    def parse(self) -> Dict[str, Any]:
        self._info["mpi4all"] = __version__
        self._info["system"] = platform.system()
        self._info["arch"] = platform.machine()

        try:
            logging.info('Checking C compiler')
            self._cc('--version')
            logging.info('C compiler OK')
        except subprocess.CalledProcessError as ex:
            raise RuntimeError(self._cc.args[0] + ' ERROR')

        try:
            logging.info('Checking C++ compiler')
            self._cxx('--version')
            logging.info('C++ compiler OK')
        except subprocess.CalledProcessError as ex:
            raise RuntimeError(self._cxx.args[0] + ' ERROR')

        try:
            logging.info('Checking mpi.h header')
            self._cc('-dM', '-E', '-include', 'mpi.h', '-')
            logging.info('mpi.h OK')
        except subprocess.CalledProcessError as ex:
            raise RuntimeError('mpi.h NOT FOUND')

        with tempfile.TemporaryDirectory() as wd:
            return self._type_fix({
                'macros': self._parse_macros(wd),
                'functions': self._parse_funcs(wd),
                'types': self._types,
                'info': self._info
            })
