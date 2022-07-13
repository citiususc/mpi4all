import os

import logging
import io

from mpi4all.version import __version__
from mpi4all.baseBuilder import BaseBuilder

KEYWORDS = {"abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class", "const", "continue",
            "default", "do", "double", "else", "enum", "extends", "final", "finally", "float", "for", "goto", "if",
            "implements", "import", "instanceof", "int", "interface", "long", "native", "new", "package", "private",
            "protected", "public", "return", "short", "static", "strictfp", "super", "switch", "synchronized", "this",
            "throw", "throws", "transient", "try", "void", "volatile", "while"}


class JavaBuilder(BaseBuilder):

    def __init__(self, class_name, package, out, lib_name, lib_out, version):
        self._class_name = class_name
        self._package = package
        self._out = out
        self._lib_name = lib_name
        self._lib_out = lib_out
        #
        self._c_source = None
        self._j_types = None
        self._j_source = None

    def _no_key(self, name):
        if name in KEYWORDS:
            return '_' + name
        return name

    def _vfun(self, vfun):
        fun = {
            'name': 'J_' + vfun['name'],
            'rtype': vfun['rtype'],
            'args': list()
        }
        self._c_source.write(vfun['rtype'] + ' ' + fun['name'] + '(')
        call = vfun['name'] + '('

        first = True
        for arg in vfun['args']:
            if '...' in arg['type']:
                break
            if not first:
                call += ', '
                self._c_source.write(', ')
            first = False
            self._c_source.write(self._c_dec(arg['type'], arg['name']))
            call += arg['name']
            fun['args'].append(arg)

        self._c_source.write('){')
        call += ');'
        if vfun['rtype'] != 'void':
            self._c_source.write('return ')
        self._c_source.write(call + '}\n')

        return fun

    def _head_types(self):
        self._j_types.write("""
        private static final Linker linker = Linker.nativeLinker();
        static {{ System.loadLibrary("{lib}"); }}
        private static final SymbolLookup lib = SymbolLookup.loaderLookup();
        
        private static MemoryLayout layout(int n){{
            return MemoryLayout.structLayout(MemoryLayout.sequenceLayout(n, ValueLayout.JAVA_BYTE));
        }}
                
        public static class Type {{
            public final MemorySegment ms;
            
            Type(String n, int sz) {{ 
                this(lib.lookup(n).get(), sz);
            }}
            
            Type(MemorySegment ms, int sz){{
                this(MemorySegment.ofAddress(ms.address(), sz, MemorySession.global()));
            }}
            
            Type(MemorySegment ms){{
                this.ms = ms;
            }}
            
            public long bytes(){{
                return ms.byteSize();
            }}
        }}

        public static class C_string extends C_pointer<C_char>{{
                
            public C_string(MemorySession session, int n){{
                super(C_char.array(session, n).ms);
            }}
            
            public C_string(MemorySession session, String v){{
                this(session, v.length() + 1);
                setString(v);
            }}
            
            public String getString(){{
                return ms.getUtf8String(0);
            }}
            
            public void setString(String v){{
                ms.setUtf8String(0, v);
            }}
                
        }}

""".format(lib=self._lib_name))

    def build(self, info):
        self._c_source = c_source = io.StringIO()
        self._j_types = j_types = io.StringIO()
        self._j_source = j_source = io.StringIO()

        c_source.write('#include <stddef.h>\n')
        c_source.write('#include <mpi.h>\n\n')

        j_types.write('package ' + self._package + ';\n')
        j_types.write("""
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;        
\n\n""")
        j_types.write('public final class ' + self._class_name + ' { \n\n')
        j_types.write((' ' * 4) + 'private ' + self._class_name + '() {}\n')
        self._head_types()

        decs = set()
        logging.info("Generating Java classes")
        classes = {
            'char': ('C_char', 'ValueLayout.JAVA_CHAR', 'char'),
            'float': ('C_float', 'ValueLayout.JAVA_FLOAT', 'float'),
            'double': ('C_double', 'ValueLayout.JAVA_DOUBLE', 'double'),
            'short': ('C_short', 'ValueLayout.JAVA_SHORT', 'short'),
            'int': ('C_int', 'ValueLayout.JAVA_INT', 'int'),
            'long': ('C_long', 'ValueLayout.JAVA_LONG', 'long'),
            'long long': ('C_long', 'ValueLayout.JAVA_LONG', 'long'),
        }
        class_template = """
        public static class {name} extends Type{{

            public {name}(String n){{
                super(n, (int){layout}.byteSize());
            }}
            
            public {name}(MemorySegment ms){{
                super(ms);
            }}
            
            public C_pointer<{name}> pointer(MemorySession session){{
                return new C_pointer(ms);
            }}
            
            public static {name} alloc(MemorySession session){{
                return new {name}(session.allocate({layout}));
            }}
            
            public static C_pointer<{name}> array(MemorySession session, int n){{
                return new C_pointer<{name}>(session.allocateArray((MemoryLayout){layout}, n));
            }}
        }}\n\n"""

        pointer_template = """
        public static class C_pointer<E> extends Type{

            public final static C_pointer<Void> NULL = of(MemorySession.global(), MemoryAddress.NULL);

            public C_pointer(String n){
                super(n, (int)ValueLayout.ADDRESS.byteSize());
            }

            public C_pointer(MemorySegment ms){
                super(ms);
            }
            
            public C_pointer<C_pointer<E>> pointer(MemorySession session){
                return of(session, ms.address());
            }
            
            public <E2> C_pointer<E2> cast(){
                return new C_pointer<E2>(ms);
            }

            public static <E> C_pointer<E> alloc(MemorySession session){
                return new C_pointer<E>(session.allocate(ValueLayout.ADDRESS));
            }

            public static <E> C_pointer<C_pointer<E>> array(MemorySession session, int n){
                return new C_pointer<C_pointer<E>>(session.allocateArray((MemoryLayout)ValueLayout.ADDRESS, n));
            }
            
            public MemoryAddress getAddress(){
                return ms.get(ValueLayout.ADDRESS, 0);
            }
            
            public void setAddress(MemoryAddress a){
                ms.set(ValueLayout.ADDRESS, 0, a);
            }
        
            static C_pointer of(MemorySession session, MemoryAddress address){
                C_pointer p = alloc(session);
                p.ms.set(ValueLayout.ADDRESS, 0, address);
                return p;
            }
            
        }\n\n"""

        pt_template = class_template[:-4] + """
            public {type} get(){{
                return ({type})ms.address().get({layout}, 0);
            }} 
            
            public void set({type} v ){{
                ms.address().set({layout}, 0, v);
            }} 
                       
            public static C_pointer<{name}> arrayOf(MemorySession session, {type}...e){{
                return new C_pointer<{name}>(session.allocateArray({layout}, e));
            }}  
        }}\n\n"""

        for key, value in sorted(classes.items(), key=lambda p: p[0]):
            if value[0] not in decs:
                j_types.write(pt_template.format(name=value[0], layout=value[1], type=value[2]))
                decs.add(value[0])

        value = ('C_pointer<Void>', 'ValueLayout.ADDRESS', None)
        j_types.write(pointer_template)
        classes['*'] = value
        decs.add(classes['*'][0])

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
                dec = class_template.format(name=j_type, layout=ly)
                if j_type not in decs:
                    j_types.write(dec)
                decs.add(c_type)
                if c_type not in classes:
                    classes[c_type] = (j_type, ly, None)

        logging.info("Generating Java variables")
        for macro in sorted(info['macros'], key=lambda m: m['name']):
            c_type = macro['type']
            c_source.write(self._c_dec(c_type, 'J_' + macro['name']))
            c_source.write(' = ' + macro['name'] + ';\n')
            j_type, _, pt = classes[c_type]
            j_source.write((' ' * 4) + 'public static final ')
            if pt:
                j_source.write(pt)
            else:
                j_source.write(j_type)
            j_source.write(' ' + macro['name'] + ' = new ')
            j_source.write(j_type + '("' + 'J_' + macro['name'] + '")')
            if pt:
                j_source.write('.get()')
            j_source.write(';\n')

        j_source.write("""
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
    }\n
    
    private static Object mpiCheck0(MpiCall mc) {
        try {
            return mc.call();
        } catch(Throwable t){
            throw new MpiException(t);
        }
    }\n
    
""")

        logging.info("Generating Java functions")
        j_types.write('\n\n')
        for fun in sorted(info['functions'], key=lambda f: f['name']):
            j_call = "C_" + fun['name'].upper()
            j_types.write(' ' * 4)
            j_types.write('private static final MethodHandle ' + j_call + ' = linker.downcallHandle(')
            j_types.write('lib.lookup("' + fun['name'] + '").get(), FunctionDescriptor.of(')

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
                j_source.write(' ' + self._no_key(arg['name']))
                j_call += self._no_key(arg['name'])
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

        path = os.path.join(self._out, self._package.replace('.', '/'))
        os.makedirs(path, exist_ok=True)
        header = '//File generated by mpi4all v' + __version__
        if 'vendor' in info['info']:
            header += ' from ' + info['info']['vendor'] + ' v' + info['info']['version'].replace('"', '')
        header += ' DO NOT EDIT.\n'
        with open(os.path.join(path, 'Mpi.java'), 'w') as class_file:
            class_file.write(header)
            class_file.write(j_types.getvalue())
            class_file.write('\n\n\n')
            class_file.write(j_source.getvalue())

        path = self._out
        if self._lib_out:
            path = self._lib_out
        path = os.path.join(path, self._lib_name)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, self._lib_name + '.c'), 'w') as class_file:
            class_file.write(header)
            class_file.write(c_source.getvalue())

        with open(os.path.join(path, 'makefile'), 'w') as makefile:
            makefile.write("""
{name}: 
\tgcc --shared -Wl,--no-as-needed -fPIC -rdynamic -lmpi {name}.c -o lib{name}.so

clean:
\trm -f lib{name}.so
""".format(name=self._lib_name))
