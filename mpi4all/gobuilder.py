import os

import logging
import io

from mpi4all.version import __version__
from mpi4all.baseBuilder import BaseBuilder

KEYWORDS = {'break', 'default', 'func', 'interface', 'select', 'case', 'defer', 'go', 'map', 'struct', 'chan', 'else',
            'goto', 'package', 'switch', 'const', 'fallthrough', 'if', 'range', 'type', 'continue', 'for', 'import',
            'return', 'var'}


class GoBuilder(BaseBuilder):

    def __init__(self, package, out, version):
        self._package = package
        self._out = out

    def _typeAsGo(self, c_type):
        go_type = 'C_' + c_type.replace('const', '').replace(' ', '')
        prefix = ''
        if '(*' in go_type and '*)' in go_type:
            s = go_type.index('(*')
            e = go_type.index('*)')
            prefix = go_type[s + 1:e + 1]
            go_type = go_type[0:s] + go_type[e + 2:]

        if '*' in go_type:
            c = go_type.count('*')
            go_type = ('*' * c) + go_type.replace('*', '')

        if '[' in go_type:
            s = go_type.index('[')
            e = go_type.index(']')
            go_type = go_type[s:e + 1] + go_type[0:s] + go_type[e + 1:]

        if ',' in go_type or '()' in go_type:
            return '*[0]byte', ''

        if 'void' in go_type:
            return 'unsafe.Pointer', None

        dec_type = go_type.replace('*', ' ').replace(']', ' ').split(' ')[-1]
        dec = 'type ' + dec_type + ' = ' + dec_type.replace('_', '.', 1) + '\n'

        return prefix + go_type, dec

    def _declare(self, dec, go_types, go_types_dec):
        if dec not in go_types_dec:
            go_types_dec.add(dec)
            go_types.write(dec)

    def _no_key(self, name):
        if name in KEYWORDS:
            return '_' + name
        return name

    def _vfun(self, vfun, c_source):
        fun = {
            'name': 'Go_' + vfun['name'],
            'rtype': vfun['rtype'],
            'args': list()
        }
        c_source.write(vfun['rtype'] + ' ' + fun['name'] + '(')
        call = vfun['name'] + '('

        first = True
        for arg in vfun['args']:
            if '...' in arg['type']:
                break
            if not first:
                call += ', '
                c_source.write(', ')
            first = False
            c_source.write(self._c_dec(arg['type'], arg['name']))
            call += arg['name']
            fun['args'].append(arg)

        c_source.write('){')
        call += ');'
        if vfun['rtype'] != 'void':
            c_source.write('return ')
        c_source.write(call + '}\n')

        return fun

    def build(self, info):
        unsafe = False
        go_types_dec = set()

        c_source = io.StringIO()
        go_types = io.StringIO()
        go_source = io.StringIO()

        c_source.write('#include <stddef.h>\n')
        c_source.write('#include <mpi.h>\n\n')
        logging.info("Generating GO variables")
        for macro in sorted(info['macros'], key=lambda m: m['name']):
            c_type = macro['type']
            c_source.write(self._c_dec(c_type, 'GO_' + macro['name']))
            c_source.write(' = ' + macro['name'] + ';\n')
            go_type, dec = self._typeAsGo(c_type)
            if dec is not None:
                self._declare(dec, go_types, go_types_dec)
            else:
                unsafe = True

            go_source.write('var ' + macro['name'] + ' ' + go_type + ' = ' + 'C.GO_' + macro['name'] + '\n')

        go_source.write("""
type MpiError struct{
    Code int
}

func (m *MpiError) Error() string {
    return "Mpi error code " + strconv.Itoa(m.Code)
}

func mpi_check(code C.int) error {
    if code == MPI_SUCCESS {
        return nil
    }
    return &MpiError{int(code)}
}
""")
        logging.info("Generating GO functions")
        for fun in sorted(info['functions'], key=lambda f: f['name']):
            go_source.write('func ' + fun['name'] + '(')
            if 'vargs' in fun:
                fun = self._vfun(fun, c_source)

            i = 0
            for arg in fun['args']:
                go_type, dec = self._typeAsGo(arg['type'])
                if dec is not None:
                    self._declare(dec, go_types, go_types_dec)
                    go_source.write(self._no_key(arg['name']) + ' ' + go_type)
                else:
                    go_source.write(self._no_key(arg['name']) + ' ' + 'unsafe.Pointer /*(' + arg['type'] + ')*/')
                    unsafe = True
                i += 1
                if i < len(fun['args']):
                    go_source.write(', ')
            go_source.write(') ')

            if fun['rtype'] == 'int':
                go_source.write('error')
            else:
                go_type, dec = self._typeAsGo(fun['rtype'])
                if dec is not None:
                    self._declare(dec, go_types, go_types_dec)
                    go_source.write(go_type)
                else:
                    go_source.write('unsafe.Pointer /*(' + fun['rtype'] + ')*/')
                    unsafe = True
            go_source.write(' {\n   return ')

            if fun['rtype'] == 'int':
                go_source.write('mpi_check(')
            go_source.write('C.' + fun['name'] + '(')
            i = 0
            for arg in fun['args']:
                go_source.write(self._no_key(arg['name']))
                i += 1
                if i < len(fun['args']):
                    go_source.write(', ')
            if fun['rtype'] == 'int':
                go_source.write(')')
            go_source.write(')\n')
            go_source.write('}\n\n')

        logging.info("Writing result")
        folder = os.path.join(os.path.abspath(self._out), self._package)
        os.makedirs(folder, exist_ok=True)
        mpi_version = None
        if 'vendor' in info['info']:
            mpi_version = info['info']['vendor'] + ' v' + info['info']['version'].replace('"', '')
        with open(os.path.join(folder, 'mpi.go'), 'w') as go_file:
            go_file.write('//File generated by mpi4all v' + __version__)
            if mpi_version:
                go_file.write(' from ' + mpi_version)
            go_file.write(' DO NOT EDIT.\n')
            go_file.write('package ' + self._package + '\n\n')
            go_file.write('/*\n#cgo LDFLAGS: -lmpi\n')
            go_file.write(c_source.getvalue())
            go_file.write('*/\nimport "C"\n')
            if unsafe:
                go_file.write('import "unsafe"\n')
            go_file.write('import "strconv"\n\n')
            go_file.write(go_types.getvalue())
            go_file.write('\n\n')
            go_file.write(go_source.getvalue())
