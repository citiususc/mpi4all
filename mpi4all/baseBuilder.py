
class BaseBuilder:

    def build(self, info):
        pass

    def _c_dec(self, c_type, c_name):
        if '*)(' in c_type:
            return c_type.replace('*)(', '*' + c_name + ')(', 1)
        elif '(' in c_type:
            return c_type.replace('(', '(*' + c_name + ')(', 1)
        elif '[' in c_type:
            return c_type.replace('[', c_name + '[', 1)
        else:
            return c_type + ' ' + c_name