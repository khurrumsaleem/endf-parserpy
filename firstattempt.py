from lark import Lark, Visitor, Transformer
from lark.reconstruct import Reconstructor
from utils import fortstr2float, float2fortstr

# [MAT, MF, MT/ content] RECORD-TYPE
# [MAT, MF, MT/ HL] TEXT

# [MAT,MF,MT/C1,C2,L1,L2,N1,N2]CONT
# [MAT,MF,MT/ZA,AWR,L1,L2,N1,N2]HEAD

# [MAT,MF,MT/blank,blank,L1,L2,N1,N2]DIR
# [MAT,MF,MT/ C1, C2, L1, L2, NPL, N2/ Bn ] LIST
# [MAT,MF,MT/ C1, C2, L1, L2, NR, NP/xint /y(x)]TAB1
# [MAT,MF,MT/ C1, C2, L1, L2, NR, NZ/ Zint ]TAB2
# [MAT, MF, MT / II, JJ, KIJ ] INTG


def read_cont(line):
    C1 = fortstr2float(line[0:11])
    C2 = fortstr2float(line[11:22])
    L1 = fortstr2float(line[22:33])
    L2 = int(line[33:44])
    N1 = int(line[44:55])
    N2 = int(line[55:66])
    return C1, C2, L1, L2, N1, N2

def write_cont(fields):
    C1 = float2fortstr(fields[0])
    C2 = float2fortstr(fields[1])
    L1 = str(fields[2]).rjust(11)
    L2 = str(fields[3]).rjust(11)
    N1 = str(fields[4]).rjust(11)
    N2 = str(fields[5]).rjust(11)
    return C1 + C2 + L1 + L2 + N1 + N2

def read_six_fancy_floats(line, blank=None):
    for i in range(0,66,11):
        if line[i:i+11] == ' '*66 and blank is None:
            pass
    assert isinstance(line, str)
    return [fortstr2float(l[i*11:(i+1)*11]) for i in range(0,6,2)]


def read_tab1_body_lines(lines, ofs, nr, np):
    NBT = []; INT = []
    for i in range(nr):
        NBT.append(int(lines[ofs+i][:11]))
        INT.append(int(lines[ofs+i][11:22]))
    ofs += nr
    xvals = []; yvals = []
    while np > 0:
        l = lines[ofs]
        m = min(6, 2*np)
        xvals += [fortstr2float(l[i*11:(i+1)*11]) for i in range(0, m, 2)] 
        yvals += [fortstr2float(l[i*11:(i+1)*11]) for i in range(1, m, 2)]
        np -= m // 2
        ofs += 1
    return {'NBT': NBT, 'INT': INT, 'X': xvals,'Y':  yvals}, ofs 

def construct_tab1_body_lines(NBT, INT, xvals, yvals):
    assert len(NBT) == len(INT)
    assert len(xvals) == len(yvals)
    lines = []
    for i in range(len(NBT)):
        curline = str(NBT[i]).rjust(11) + str(INT[i]).rjust(11) + ' '*44 
        lines.append(curline)
    elcnt = 0
    curline = ''
    for x, y in zip(xvals, yvals):
        curline += float2fortstr(x, width=11) + float2fortstr(y, width=11) 
        elcnt += 2
        if elcnt == 6:
            elcnt = 0
            lines.append(curline)
            curline = ''
    if elcnt != 0:
        lines.append(curline)
    return lines

        

class EndfConverter(Visitor):

    def __update_dic(self, varnames, values):
        ret = []
        for i, vn in enumerate(varnames):
            vns = vn.strip()
            if vns not in ('0', '0.0'):
                self.__datadic[vn] = values[i]

    def __extract_vals(self, varnames):
        vals = []
        for i, vn in enumerate(varnames):
            vns = vn.strip()
            if vns not in ('0', '0.0'):
                vals.append(self.__datadic[vn])
            else:
                vals.append(vns.rjust(11))
        return vals

    def head_fields(self, tree):
        varnames = [str(tok) for tok in tree.children]
        if 'ZA' not in varnames or 'AWR' not in varnames:
            raise TypeError('The first two fields of a HEAD record must be named ZA and AWR')
        if self.__mode == 'read':
            values = read_cont(self.__lines[self.__ofs])
            self.__update_dic(varnames, values)
        else:
            values = self.__extract_vals(varnames)
            self.__lines.append(write_cont(values))
        self.__ofs += 1

    def cont_fields(self, tree):
        varnames = [str(tok) for tok in tree.children]
        if self.__mode == 'read': 
            values = read_cont(self.__lines[self.__ofs])
            self.__update_dic(varnames, values)
        else:
            values = self.__extract_vals(varnames)
            self.__lines.append(write_cont(values))
        self.__ofs += 1

    def tab1_line(self, tree):
        t1 = list(tree.find_pred(lambda x: x.data == 'tab1_cont_fields'))
        t2 = list(tree.find_pred(lambda x: x.data == 'tab1_def'))
        t3 = list(tree.find_pred(lambda x: x.data == 'table_name'))
        assert len(t1) == 1 and len(t2) == 1
        assert len(t3) == 0 or len(t3) == 1
        tblname = 'table' if len(t3)==0 else t3[0].children[0].value
        varnames = [tok.value for tok in t1[0].children]
        tblcolnames = [tok.value for tok in t2[0].children] 
        assert varnames[4] == 'NR' and varnames[5] == 'NP'
        if self.__mode == 'read':
            values = read_cont(self.__lines[self.__ofs])
            self.__ofs += 1
            self.__update_dic(varnames[:4], values[:4])
            tbl, self.__ofs = read_tab1_body_lines(self.__lines,
                    self.__ofs, int(values[4]), int(values[5]))
            tbl[tblcolnames[0]] = tbl.pop('X')
            tbl[tblcolnames[1]] = tbl.pop('Y')
            self.__datadic[tblname] = tbl
        else:
            values = self.__extract_vals(varnames[:4])
            tbl = self.__datadic[tblname] 
            nr = len(tbl['NBT'])
            np = len(tbl[tblcolnames[0]])
            values += [str(nr).rjust(11), str(np).rjust(11)]
            tbllines = construct_tab1_body_lines(
                    tbl['NBT'], tbl['INT'], tbl[tblcolnames[0]], tbl[tblcolnames[1]])
            self.__lines.append(write_cont(values))
            self.__lines += tbllines
            bla = self.__lines
            self.__ofs += 1 + len(tbllines) 

    def endf2dic(self, lines, tree):
        self.__ofs = 0
        self.__datadic = {}
        lines = [l for l in lines if l.strip()]
        self.__lines = lines
        self.__mode = 'read'
        super().visit(tree)
        return self.__datadic

    def dic2endf(self, datadic, tree):
        self.__ofs = 0
        self.__datadic = datadic
        self.__lines = []
        self.__mode = 'write'
        super().visit(tree)
        return self.__lines


from endf_spec import endf_spec_mf3_mt as curspec
from endf_snippets import endf_cont_mf3_mt16 as curcont

with open('endf.lark', 'r') as f:
    mygrammar = f.read()

myparser = Lark(mygrammar, start='endf_format')
tree = myparser.parse(curspec)
print(tree.pretty())

mylines = curcont.splitlines()
converter = EndfConverter()
datadic = converter.endf2dic(mylines, tree)
newline = converter.dic2endf(datadic, tree)
#print(mylines)
#print(datadic)
print('\n'.join(newline))

