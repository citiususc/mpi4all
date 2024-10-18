import os

import io
import string
import logging
from typing import Tuple, Optional, Dict
from mpi4all.generator.base import BaseGenerator

_KEYWORDS = {"abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class", "const", "continue",
             "default", "do", "double", "else", "enum", "extends", "final", "finally", "float", "for", "goto", "if",
             "implements", "import", "instanceof", "int", "interface", "long", "native", "new", "package", "private",
             "protected", "public", "return", "short", "static", "strictfp", "super", "switch", "synchronized", "this",
             "throw", "throws", "transient", "try", "void", "volatile", "while"}

_J_LOAD_LIBRARY_TEMPLATE = string.Template("""\
    static { 
        if (System.getProperty("${lib}.path", null) != null){
            System.loadLibrary(new java.io.File("${lib}").getAbsolutePath()); 
        } else {
            try {
                System.loadLibrary("${lib}"); 
            } catch (Exception ex1) {
                try {
                    if (${class_name}.class.getClassLoader().getResource("${lib}.so") != null) {
                        var tmp = java.nio.file.Files.createTempFile("${lib}", ".so");
                        tmp.toFile().deleteOnExit();
                        try (var is = ${class_name}.class.getClassLoader().getResourceAsStream("${lib}.so")) {
                            java.nio.file.Files.copy(is, tmp);
                        }
                        System.load(tmp.toAbsolutePath().toString());
                    } else {
                        throw new RuntimeException(ex1);
                    }
                } catch (Exception ex2) {
                    throw new RuntimeException(ex2);
                }
            }
        }
    }
""")

_J_CLASS_HEADER = string.Template("""\
    private static final Linker linker = Linker.nativeLinker();
    private static final SymbolLookup lib = SymbolLookup.loaderLookup();
    
    private static MemoryLayout layout(int n){
        return MemoryLayout.structLayout(MemoryLayout.sequenceLayout(n, ValueLayout.JAVA_BYTE));
    }
    
    private static MethodHandle findMethod(String name, FunctionDescriptor function){
        java.util.Optional<MemorySegment> ms = lib.find(name);
        if (ms.isEmpty()){
            return null;
        }
        return linker.downcallHandle(ms.get(), function);
    }
            
    public static class Type {
        public final MemorySegment ms;
        
        Type(String n, int sz) {
            this(lib.find(n).get(), sz);
        }
        
        Type(MemorySegment ms, int sz){
            this(ms.reinterpret(sz, Arena.ofAuto(), null));
        }
        
        Type(MemorySegment ms){
            this.ms = ms;
        }
        
        public long bytes(){
            return ms.byteSize();
        }
        
        public void to(MemorySegment ms){
            ms.copyFrom(this.ms);
        }
    }
    
    public static class C_pointer<E> extends Type{

        public final static C_pointer<Void> NULL = new C_pointer(MemorySegment.NULL);

        public C_pointer(String n){
            super(n, 0);
        }

        public C_pointer(MemorySegment ms){
            super(ms);
        }
        
        public C_pointer<C_pointer<E>> pointer(Arena a){
            MemorySegment p = a.allocate(ValueLayout.ADDRESS);
            p.set(ValueLayout.ADDRESS, 0, ms);
            return new C_pointer<>(p);
        }
        
        public C_pointer<C_pointer<E>> pointer(){
            return pointer(Arena.ofAuto());
        }
        
        public <E2> C_pointer<E2> cast(){
            return new C_pointer<E2>(ms);
        }
        
        public static <E> C_pointer<E> from(Arena a, MemorySegment ms){
            return new C_pointer<E>(ms);
        }
        
        public static <E> C_pointer<E> from(MemorySegment ms){
            return from(Arena.ofAuto(), ms);
        }
        
        public MemorySegment getAddress(){
            return ms.reinterpret((int)ValueLayout.ADDRESS.byteSize(), Arena.ofAuto(), null).get(ValueLayout.ADDRESS, 0);
        }
        
    }
    
    public static class C_string extends C_pointer<C_char>{
            
        public C_string(Arena a, int n){
            super(C_char.array(a, n).ms);
        }
        
        public C_string(int n){
            super(C_char.array(n).ms);
        }
        
        public C_string(Arena a, String v){
            this(a, v.length() + 1);
            setString(v);
        }
        
        public C_string(String v){
            this(Arena.ofAuto(), v);
        }
        
        public String getString(){
            return ms.get${Utf8}String(0);
        }
        
        public void setString(String v){
            ms.set${Utf8}String(0, v);
        }
    }
""")

_J_CLASS_TEMPLATE = string.Template("""\
    public static class ${name} extends Type{
        
        public ${name}(String n){
            super(n, (int)${layout}.byteSize());
        }
    
        public static int byteSize(){
            return (int)${layout}.byteSize();
        }
    
        public ${name}(MemorySegment ms){
            super(ms);
        }
    
        public C_pointer<${name}> pointer(){
            return new C_pointer<${name}>(ms);
        }
    
        public C_pointer<${name}> pointer(Arena a){
            return new C_pointer<${name}>(ms);
        }
    
        public ${name} copy(){
            return from(Arena.ofAuto(), this.ms);
        }
        
        public ${name} copy(Arena a){
            return from(a, this.ms);
        }
    
        public static ${name} alloc(Arena a){
            return new ${name}(a.allocate(${layout}));
        }
    
        public static ${name} alloc(){
            return alloc(Arena.ofAuto());
        }
    
        public static ${name} from(Arena a, MemorySegment ms){
            return new ${name}(a.allocate(ms.byteSize()).copyFrom(ms));
        }
    
        public static ${name} from(MemorySegment ms){
            return from(Arena.ofAuto(), ms);
        }
    
        public static C_pointer<${name}> array(Arena a, int n){
            return new C_pointer<${name}>(a.allocate${Array}((MemoryLayout)${layout}, n));
        }
    
        public static C_pointer<${name}> array(int n){
            return array(Arena.ofAuto(), n);
        }
    }\n
""")

_J_BASICS: Dict[str, Tuple[str, str, Optional[str]]] = {
    'char': ('C_char', 'ValueLayout.JAVA_CHAR', 'char'),
    'float': ('C_float', 'ValueLayout.JAVA_FLOAT', 'float'),
    'double': ('C_double', 'ValueLayout.JAVA_DOUBLE', 'double'),
    'short': ('C_short', 'ValueLayout.JAVA_SHORT', 'short'),
    'int': ('C_int', 'ValueLayout.JAVA_INT', 'int'),
    'long': ('C_long', 'ValueLayout.JAVA_LONG', 'long'),
    'long long': ('C_long', 'ValueLayout.JAVA_LONG', 'long'),
}

_J_BASIC_TEMPLATE = string.Template(_J_CLASS_TEMPLATE.template[:_J_CLASS_TEMPLATE.template.rindex('}') - 1] + """\
        public ${name}(${type} v){
            this(Arena.ofAuto(), v);
        }
        
        public ${name}(Arena a, ${type} v){
            super(${name}.alloc(a).ms);
            set(v);
        }

        public ${type} get(){
            return (${type})ms.get(${layout}, 0);
        } 
    
        public ${name} set(${type} v ){
            ms.set(${layout}, 0, v);
            return this;
        } 
    
        public static C_pointer<${name}> arrayOf(Arena a, ${type}...e){
            return new C_pointer<${name}>(a.allocate${From}(${layout}, e));
        }  
    
        public static C_pointer<${name}> arrayOf(${type}...e){
            return arrayOf(Arena.ofAuto(), e);
        } 
    }\n
""")

_J_ERROR_CHECK = """\
    @FunctionalInterface
    public interface MpiCall {
        Object call() throws Throwable;
    }
    
    public static final class MpiException extends RuntimeException{
        private final int code;
        
        MpiException(int c){
            super("Mpi error code " + c);
            code = c;
        }
        
        MpiException(Throwable t){
            super(t);
            code = 0;
        }
        
        public int getCode() {
            return code;
        }
    }
        
    private static void mpiCheck(MpiCall mc) {
        try {
            int c = (int)mc.call();
            if (c != MPI_SUCCESS) {
                throw new MpiException(c);
            }
        } catch(Throwable t){
            throw new MpiException(t);
        }
    }
    
    private static Object mpiCheck0(MpiCall mc) {
        try {
            return mc.call();
        } catch(Throwable t){
            throw new MpiException(t);
        }
    }    
"""

_J_MAKEFILE_TEMPLATE = string.Template("""
all: 
\tgcc --shared -Wl,--no-as-needed -fPIC -rdynamic -lmpi ${name}.c -o lib${name}.so

clean:
\trm -f lib${name}.so
""")


class JavaGenerator(BaseGenerator):

    def __init__(self, class_name: str, package: str, out: str, lib_name: str, lib_out: str, jdk21: bool):
        super().__init__()
        self._class_name = class_name
        self._package = package
        self._out = out
        self._lib_name = lib_name
        self._lib_out = lib_out
        self._jdk21 = jdk21
        #
        self._j_types = io.StringIO()
        self._j_source = io.StringIO()
        self._classes = _J_BASICS.copy()

    def _safe_key(self, name: str) -> str:
        if name in _KEYWORDS:
            return '_' + name
        return name

    def _write_macro(self, macro: Dict[str, str]):
        j_source = self._j_source
        if not macro['var']:
            return

        j_type, _, pt = self._classes[macro['type']]
        j_source.write((' ' * 4) + 'public static final ')
        if pt:
            j_source.write(pt)
        else:
            j_source.write(j_type)
        j_source.write(' ' + macro['name'] + ' = new ')
        j_source.write(j_type + '("' + self._prefix + macro['name'] + '")')
        if pt:
            j_source.write('.get()')
        j_source.write(';\n')

    def build(self, info):
        j_types = self._j_types
        j_source = self._j_source

        j_types.write(f'package {self._package};\n')
        j_types.write(f'import java.lang.foreign.*;\n')
        j_types.write(f'import java.lang.invoke.MethodHandle;\n')
        j_types.write('\n\n')
        j_types.write(f'public final class {self._class_name} {{ \n\n')
        j_types.write(f'    private {self._class_name} (){{}}\n')
        j_types.write(_J_LOAD_LIBRARY_TEMPLATE.substitute(lib=self._lib_name, class_name=self._class_name))
        j_types.write(_J_CLASS_HEADER.substitute(Utf8='Utf8' if self._jdk21 else ''))

        type_decs = set()
        classes = self._classes
        if 'MPI_Count' in info['types']:
            classes['MPI_Count'] = classes[info['types']['MPI_Count']]
        for key, value in sorted(classes.items(), key=lambda p: p[0]):
            if value[0] not in type_decs:
                j_types.write(_J_BASIC_TEMPLATE.substitute(name=value[0], layout=value[1], type=value[2],
                                                           From='Array' if self._jdk21 else 'From',
                                                           Array='Array' if self._jdk21 else ''))
                type_decs.add(value[0])
        classes['*'] = ('C_pointer<Void>', 'ValueLayout.ADDRESS', None)
        type_decs.add(classes['*'][0])

        logging.info("Generating Java classes")

        for c_type, ref in sorted(info['types'].items(), key=lambda p: p[0]):
            j_type = c_type.replace('const ', '').replace(' ', '')
            base = j_type.split('[')[0].replace('*', '').strip()

            if j_type in classes:
                classes[c_type] = classes[j_type]

            elif '(' in j_type:
                classes[c_type] = classes['*']

            elif base in classes and base and j_type != base:
                values = classes[base]
                plevel = j_type.count('*') + j_type.count('[')
                pointer = 'C_pointer<{E}>'
                j_type = '{E}'
                for i in range(plevel):
                    j_type = j_type.format(E=pointer)
                j_type = j_type.format(E=values[0])
                classes[c_type] = (j_type, classes['*'][1], None)

            elif '*' in j_type or '[' in j_type:
                classes[c_type] = classes['*']

            elif c_type.isidentifier() and c_type not in classes:
                if not j_type.startswith("MPI_"):
                    j_type = 'C_' + j_type
                bytes = ref if ref.isdigit() else info['types'][ref]
                ly = 'layout(' + bytes + ')'
                dec = _J_CLASS_TEMPLATE.substitute(name=j_type, layout=ly, Array='Array' if self._jdk21 else '')
                if j_type not in type_decs:
                    j_types.write(dec)
                type_decs.add(c_type)
                if c_type not in classes:
                    classes[c_type] = (j_type, ly, None)

        logging.info("Generating Java variables")
        self._build_macros(info)
        j_source.write('\n\n')
        j_source.write(_J_ERROR_CHECK)
        j_source.write('\n')

        logging.info("Generating Java functions")
        j_types.write('\n')
        for fun in sorted(info['functions'], key=lambda f: f['name']):
            j_call = "C_" + fun['name'].upper()
            j_types.write(' ' * 4)
            j_types.write('private static final MethodHandle ' + j_call + ' = findMethod(')
            j_types.write('"' + fun['name'] + '", FunctionDescriptor.of(')

            j_source.write(' ' * 4)
            j_source.write('public static ')
            rcast = None
            _return = None
            if fun['rtype'] == 'int':
                j_source.write('void')
                j_types.write('ValueLayout.JAVA_INT')
            else:
                c_type = fun['rtype']
                j_type, ly, tp = classes[c_type]
                j_types.write(ly)
                if tp:
                    rcast = '(' + tp + ')'
                    j_source.write(tp)
                else:
                    j_source.write('void')
                    _return = ''
                    if j_type == 'C_pointer<Void>':
                        _return += '/*(' + fun['rtype'] + ')*/'
                    _return += j_type + ' _return, '

            j_source.write(' ' + fun['name'] + '(')
            if 'vargs' in fun:
                fun = self._vfun(fun)

            i = 0
            j_call += '.invoke('
            if _return:
                j_source.write(_return)
                j_call += '_return, '

            for arg in fun['args']:
                c_type = arg['type']
                j_type, ly, pt = classes[c_type]
                j_types.write(', ' + ly)
                if j_type == 'C_pointer<Void>':
                    j_source.write('/*(' + c_type + ')*/ ')
                if pt:
                    j_source.write(pt)
                else:
                    j_source.write(j_type)
                j_source.write(' ' + self._safe_key(arg['name']))
                j_call += self._safe_key(arg['name'])
                if not pt:
                    j_call += '.ms'

                i += 1
                if i < len(fun['args']):
                    j_source.write(', ')
                    j_call += ', '
            j_types.write('));\n')
            j_source.write(') {\n')

            j_source.write(' ' * 8)
            if fun['rtype'] != 'int' and not _return:
                j_source.write('return ')
                if rcast:
                    j_source.write(rcast)
                j_source.write('mpiCheck0(()->')
            else:
                j_source.write('mpiCheck(()->')

            j_source.write(j_call + '))')
            j_source.write(';\n')
            j_source.write(' ' * 4)
            j_source.write('}\n\n')
        j_source.write('}\n')

        logging.info("Generating Go binding sources")
        header = f'//{self._header_message(info)}\n'
        path = os.path.join(self._out, self._package.replace('.', '/'))
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, f'{self._class_name}.java'), 'w') as class_file:
            class_file.write(header)
            class_file.write(j_types.getvalue())
            class_file.write('\n\n')
            class_file.write(j_source.getvalue())

        lib_path = os.path.join(self._lib_out, self._lib_name)
        os.makedirs(lib_path, exist_ok=True)
        with open(os.path.join(lib_path, self._lib_name + '.c'), 'w') as class_file:
            class_file.write(header)
            class_file.write(self._c_source.getvalue())

        with open(os.path.join(lib_path, 'makefile'), 'w') as makefile:
            makefile.write(_J_MAKEFILE_TEMPLATE.substitute(name=self._lib_name))
