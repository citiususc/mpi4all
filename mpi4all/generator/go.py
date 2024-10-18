import os

import logging
import io
from typing import Dict

from mpi4all.generator.base import BaseGenerator

_KEYWORDS = {'break', 'default', 'func', 'interface', 'select', 'case', 'defer', 'go', 'map', 'struct', 'chan', 'else',
             'goto', 'package', 'switch', 'const', 'fallthrough', 'if', 'range', 'type', 'continue', 'for', 'import',
             'return', 'var'}

_GO_ERROR_CHECK = """\
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
"""

_GO_TYPES = """\
type C_int64 = C.int64_t
type C_int32 = C.int16_t
type C_int16 = C.int32_t
type C_int8 = C.int8_t      
"""

_GO_FUNCTIONS = """\
func C_ArrayToString(array []C_char) string {
    str := C.GoString(&array[0])
    return strings.Clone(str)
}

func C_ArrayFromString(str string) []C_char {
    array := make([]C_char, len(str)+1)
    for i, c := range str {
        array[i] = C_char(c)
    }
    array[len(str)] = '\\x00'
    return array
}  

func C_NULL() unsafe.Pointer { return unsafe.Pointer(nil) }

func C_Memcpy(dest unsafe.Pointer, src unsafe.Pointer, size int) {
    C.memcpy(dest, src, C.size_t(size))
} 
"""

_GO_GENERIC_FUNCTIONS = """\
func P[T any](ptr *T) unsafe.Pointer {
    return unsafe.Pointer(ptr)
}

var none C_int

func PA[T any](ptr *[]T) unsafe.Pointer {
    if len(*ptr) > 0 {
        return unsafe.Pointer(&((*ptr)[0]))
    }
    return unsafe.Pointer(&none)
}
"""


class GoGenerator(BaseGenerator):

    def __init__(self, package: str, generic: str, out: str):
        super().__init__()
        self._package = package
        self._generic = generic
        self._out = out
        #
        self._unsafe = False
        self._go_types_dec = set()
        self._go_types = io.StringIO()
        self._go_source = io.StringIO()

    def _typeAsGo(self, c_type: str):
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

    def _declare(self, dec: str):
        if dec not in self._go_types_dec:
            self._go_types_dec.add(dec)
            self._go_types.write(dec)

    def _safe_key(self, name: str) -> str:
        if name in _KEYWORDS:
            return '_' + name
        return name

    def _write_macro(self, macro: Dict[str, str]):
        if not macro['var']:
            go_type, dec = self._typeAsGo(self._prefix + macro['name'])
            if dec is not None:
                self._declare(dec.replace(self._prefix, '', 1))
        else:
            go_type, dec = self._typeAsGo(macro['type'])
            if dec is not None:
                self._declare(dec)
            else:
                self.unsafe = True

            self._go_source.write(
                'var ' + macro['name'] + ' ' + go_type + ' = ' + f'C.{self._prefix}' + macro['name'] + '\n')

    def build(self, info):
        go_source = self._go_source

        logging.info('Generating GO variables')
        self._build_macros(info)
        go_source.write('\n\n')
        go_source.write(_GO_ERROR_CHECK)
        go_source.write('\n')

        logging.info('Generating GO functions')
        for fun in sorted(info['functions'], key=lambda f: f['name']):
            go_source.write('func ' + fun['name'] + '(')
            if 'vargs' in fun:
                fun = self._vfun(fun)

            i = 0
            for arg in fun['args']:
                go_type, dec = self._typeAsGo(arg['type'])
                if dec is not None:
                    self._declare(dec)
                    go_source.write(self._safe_key(arg['name']) + ' ' + go_type)
                else:
                    go_source.write(self._safe_key(arg['name']) + ' ' + 'unsafe.Pointer /*(' + arg['type'] + ')*/')
                    self._unsafe = True
                i += 1
                if i < len(fun['args']):
                    go_source.write(', ')
            go_source.write(') ')

            if fun['rtype'] == 'int':
                go_source.write('error')
            else:
                go_type, dec = self._typeAsGo(fun['rtype'])
                if dec is not None:
                    self._declare(dec)
                    go_source.write(go_type)
                else:
                    go_source.write('unsafe.Pointer /*(' + fun['rtype'] + ')*/')
                    self._unsafe = True
            go_source.write(' {\n   return ')

            if fun['rtype'] == 'int':
                go_source.write('mpi_check(')
            go_source.write('C.' + fun['name'] + '(')
            i = 0
            for arg in fun['args']:
                go_source.write(self._safe_key(arg['name']))
                i += 1
                if i < len(fun['args']):
                    go_source.write(', ')
            if fun['rtype'] == 'int':
                go_source.write(')')
            go_source.write(')\n')
            go_source.write('}\n\n')

        go_source.write(_GO_TYPES)
        go_source.write(_GO_FUNCTIONS)
        if self._generic:
            go_source.write(_GO_GENERIC_FUNCTIONS)

        logging.info('Generating Go binding sources')
        folder = os.path.join(os.path.abspath(self._out), self._package)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, 'mpi.go'), 'w') as go_file:
            go_file.write(f'//{self._header_message(info)}\n')

            go_file.write('package ' + self._package + '\n\n')
            go_file.write('/*\n#cgo LDFLAGS: -lmpi\n')
            go_file.write(self._c_source.getvalue())
            go_file.write('*/\nimport "C"\n')
            if self.unsafe:
                go_file.write('import "unsafe"\n')
            go_file.write('import "strings"\n')
            go_file.write('import "strconv"\n\n')
            go_file.write(self._go_types.getvalue())
            go_file.write('\n\n')
            go_file.write(go_source.getvalue())
