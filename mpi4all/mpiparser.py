import os.path
import subprocess
import tempfile
import re
from concurrent.futures import ThreadPoolExecutor
import logging


class MpiParser:
    CAST_RE = re.compile(r'^\(?\((MPI_\w+[ *]*)\)|OMPI_PREDEFINED_GLOBAL\([ ]*(MPI_\w+[ *]*)')

    def __init__(self, gcc, gpp, mpih, exclude_list, get_func_args):
        self._gcc = [gcc, '-I' + mpih] if mpih else [gcc]
        self._gpp = [gpp, '-I' + mpih] if mpih else [gpp]
        self._exclude_patterns = list(map(lambda e: re.compile(e), exclude_list))
        self._get_func_args = get_func_args
        self._types = dict()
        self._info = dict()

        try:
            logging.info('Checking C compiler')
            self._run(self._gcc + ['--version'])
            logging.info('C compiler OK')
        except subprocess.CalledProcessError as ex:
            raise RuntimeError(self._gcc[0] + ' not found')

        try:
            logging.info('Checking C++ compiler')
            self._run(self._gpp + ['--version'])
            logging.info('C++ compiler OK')
        except subprocess.CalledProcessError as ex:
            raise RuntimeError(self._gpp[0] + ' not found')

        try:
            logging.info('Checking header mpi.h')
            self._run(self._gcc + ['-dM', '-E', '-include', 'mpi.h', '-'])
            logging.info('Header mpi.h OK')
        except subprocess.CalledProcessError as ex:
            raise RuntimeError('mpi.h not found')

    def _run(self, args, input='', check=True):
        return subprocess.run(args, check=check, capture_output=True, text=True, input=input)

    def _exclude(self, s):
        for pattern in self._exclude_patterns:
            if pattern.search(s):
                return True
        return False

    def _c_info(self, name, wd):
        src = """
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
                          std::cout << std::endl;
                      }}
                      std::cout << sizeof({name}) <<std::endl;
                  }}
                  """.format(name=name)

        bin = os.path.join(wd, name)
        cpp = bin + '.cpp'

        with open(cpp, mode='w') as file:
            file.write(src)
            file.flush()

        try:
            self._run(self._gpp + ['-fpermissive', cpp, '-o', bin])
            typename, bytes = self._run([bin]).stdout.split('\n')[:2]

            i = 'auto x = ' + name + ';'
            if self._run(self._gpp + ['--shared', '-include', 'mpi.h', '-o', '/dev/null', '-x', 'c++', '-'],
                         check=False, input=i).returncode == 0:
                var = True
            else:
                var = False

            return typename, var, bytes, None
        except subprocess.CalledProcessError as ex:
            return None, None, None, ex.stderr

    def _parse_macro(self, macro, wd):
        r = {'raw': macro}
        if not macro.startswith('#define MPI_') or self._exclude(macro):
            if '_VERSION' in macro:
                name, value = macro.split(' ', 2)[1:]
                if 'MPICH_VERSION' in macro:
                    self._info['vendor'] = 'mpich'
                    self._info['version'] = value
                elif 'OMPI_MAJOR_VERSION' in macro:
                    self._info['vendor'] = 'open-mpi'
                    self._info['version_1'] = '"' + value
                elif 'OMPI_MINOR_VERSION ' in macro:
                    self._info['vendor'] = 'open-mpi'
                    self._info['version_2'] = '.' + value + '.'
                elif 'OMPI_RELEASE_VERSION' in macro:
                    self._info['vendor'] = 'open-mpi'
                    self._info['version_3'] = value + '"'

            r['error'] = False
            return r

        line = macro.split(' ', 1)[1]
        name = None
        value = None
        for i in range(len(line)):
            if line[:-i].isidentifier():
                name = line[:-i]
                value = line[len(name):].strip()
                break

        if name is None:
            return r

        r['name'] = name
        r['value'] = value

        typename, var, bytes, error = self._c_info(name, wd)
        if error:
            r['error'] = error
            return r

        r['type'] = typename
        r['bytes'] = bytes
        r['var'] = var
        cast = MpiParser.CAST_RE.match(value)
        if cast:
            r['mtype'] = (cast.group(1) if cast.group(1) else cast.group(2)).strip()

        return r

    def _parse_macros(self, wd):
        logging.info('getting macros')
        macro_dump = self._run(self._gcc + ['-dM', '-E', '-include', 'mpi.h', '-']).stdout
        with ThreadPoolExecutor() as workers:
            logging.info('parsing macros')
            all_macros = workers.map(lambda m: self._parse_macro(m, wd), macro_dump.split('\n'))
        macros = list()
        for m in all_macros:
            if 'error' in m:
                if m['error']:
                    logging.warning(m['raw'] + ' ignored ' + m['error'])
            else:
                self._types[m['type']] = m['bytes']
                if '*' in m['type']:
                    self._types['*'] = m['bytes']
                del m['bytes']
                if 'mtype' in m:
                    self._types[m['mtype']] = m['type']
                    m['type'] = m['mtype']
                    del m['mtype']

                macros.append(m)

        if 'version_1' in self._info:
            version = ''
            i = 1
            while 'version_' + str(i) in self._info:
                version += self._info['version_' + str(i)]
                del self._info['version_' + str(i)]
                i += 1
            self._info['version'] = version

        return macros

    def _parse_funcs(self, wd):
        func_file = os.path.join(wd, 'func.X')
        self._run(
            self._gcc + ['-x', 'c', '-shared', '-o', '/dev/null', '-aux-info', func_file, '-include', 'mpi.h', '-'])

        with open(func_file) as file:
            func_dump = file.readlines()

        functions = list()
        for raw in func_dump:
            f = {}
            try:
                header = raw[min(raw.index('*/') + 2, len(raw)):].strip()
                if header.startswith('extern'):
                    header = header.replace('extern', '', 1)
            except ValueError:
                continue
            if not header:
                continue

            def search(arg):
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

            header = header.replace(';', '').strip()
            f['header'] = header

            rt, header = header.split(' ', 1)
            f['rtype'] = rt.strip()
            header = header.strip()

            fn, header = header.split('(', 1)
            f['name'] = fn.strip()
            header = header.strip()
            if not f['name'].startswith('MPI_') or self._exclude(f['name']):
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
                    search(arg)

            search(f['rtype'])
            if len(f['args']) == 1 and f['args'][0]['type'] == 'void':
                f['args'].clear()

            if 'error' not in f:
                functions.append(f)

        if self._get_func_args:
            name_info = self._run(self._gcc + ['-E', '-include', 'mpi.h', '-']).stdout
            for f in functions:
                try:
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
                except Exception as ex:
                    logging.info(f['name'] + ' param names not found')
                    for i in range(len(f['args'])):
                        f['args'][i]['name'] = 'x' + str(i)
        else:
            for f in functions:
                for i in range(len(f['args'])):
                    f['args'][i]['type'] = 'x' + str(i)

        return functions

    def _type_fix(self, result):
        if 'vendor' in self._info and self._info['vendor'] == 'open-mpi':
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

    def parse(self):
        with tempfile.TemporaryDirectory() as wd:
            return self._type_fix({
                'macros': self._parse_macros(wd),
                'functions': self._parse_funcs(wd),
                'types': self._types,
                'info': self._info
            })
