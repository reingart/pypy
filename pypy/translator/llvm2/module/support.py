extdeclarations = """
declare ccc double %pow(double, double)
declare ccc double %fmod(double, double)
"""


extfunctions = {}

extfunctions["%cast"] = ((), """
internal fastcc sbyte* %cast(%structtype.rpy_string* %structstring) {
    %source1ptr = getelementptr %structtype.rpy_string* %structstring, int 0, uint 1, uint 1
    %source1 = cast [0 x sbyte]* %source1ptr to sbyte*
    ret sbyte* %source1
}

""")


#abs functions
extfunctions["%int_abs"] = ((), """
internal fastcc int %int_abs(int %x) {
block0:
    %cond1 = setge int %x, 0
    br bool %cond1, label %return_block, label %block1
block1:
    %x2 = sub int 0, %x
    br label %return_block
return_block:
    %result = phi int [%x, %block0], [%x2, %block1]
    ret int %result
}

""")

extfunctions["%float_abs"] = ((), """
internal fastcc double %float_abs(double %x) {
block0:
    %cond1 = setge double %x, 0.0
    br bool %cond1, label %return_block, label %block1
block1:
    %x2 = sub double 0.0, %x
    br label %return_block
return_block:
    %result = phi double [%x, %block0], [%x2, %block1]
    ret double %result
}

""")


#prepare exceptions
for exc in "ZeroDivisionError OverflowError ValueError".split():    #_ZER _OVF _VAL
    extfunctions["%%__prepare_%(exc)s" % locals()] = ((), """
internal fastcc void %%__prepare_%(exc)s() {
    %%exception_value = call fastcc %%structtype.object* %%instantiate_%(exc)s()
    %%tmp             = getelementptr %%structtype.object* %%exception_value, int 0, uint 0
    %%exception_type  = load %%structtype.object_vtable** %%tmp
    store %%structtype.object_vtable* %%exception_type, %%structtype.object_vtable** %%last_exception_type
    store %%structtype.object* %%exception_value, %%structtype.object** %%last_exception_value
    ret void
}
""" % locals())


#error-checking-code

zer_test = """
    %%cond = seteq %s %%y, 0
    br bool %%cond, label %%is_0, label %%is_not_0
is_0:
    call fastcc void %%__prepare_ZeroDivisionError()
    unwind

is_not_0:
"""
int_zer_test    = zer_test % ('int',)
double_zer_test = zer_test % ('double',)


#overflow: normal operation, ...if ((x) >= 0 || (x) != -(x)) OK else _OVF()
#note: XXX this hardcoded int32 minint value is used because of a pre llvm1.6 bug!

int_ovf_test = """
    %cond2 = setne int %x, -2147483648
    br bool %cond2, label %return_block, label %ovf
ovf:
    call fastcc void %__prepare_OverflowError()
    unwind
"""


#binary with ZeroDivisionError only

for func_inst in "floordiv_zer:div mod_zer:rem".split():
    func, inst = func_inst.split(':')
    for type_ in "int uint".split():
        type_zer_test = zer_test % type_
        extfunctions["%%%(type_)s_%(func)s" % locals()] = (("%__prepare_ZeroDivisionError",), """
internal fastcc %(type_)s %%%(type_)s_%(func)s(%(type_)s %%x, %(type_)s %%y) {
    %(type_zer_test)s
    %%z = %(inst)s %(type_)s %%x, %%y
    ret %(type_)s %%z
}

""" % locals())


#unary with OverflowError only

extfunctions["%int_neg_ovf"] = (("%__prepare_OverflowError",), """
internal fastcc int %%int_neg_ovf(int %%x) {
block1:
    %%x2 = sub int 0, %%x
    %(int_ovf_test)s
return_block:
    ret int %%x2
}
""" % locals())

extfunctions["%int_abs_ovf"] = (("%__prepare_OverflowError",), """
internal fastcc int %%int_abs_ovf(int %%x) {
block0:
    %%cond1 = setge int %%x, 0
    br bool %%cond1, label %%return_block, label %%block1
block1:
    %%x2 = sub int 0, %%x
    %(int_ovf_test)s
return_block:
    %%result = phi int [%%x, %%block0], [%%x2, %%block1]
    ret int %%result
}
""" % locals())


#binary with OverflowError only

extfunctions["%int_add_ovf"] = (("%__prepare_OverflowError",), """
internal fastcc int %%int_add_ovf(int %%x, int %%y) {
    %%t = add int %%x, %%y
    %(int_ovf_test)s
return_block:
    ; XXX: TEST int_add_ovf checking
    ret int %%t
}
""" % locals())

extfunctions["%int_sub_ovf"] = (("%__prepare_OverflowError",), """
internal fastcc int %%int_sub_ovf(int %%x, int %%y) {
    %%t = sub int %%x, %%y
    %(int_ovf_test)s
return_block:
    ; XXX: TEST int_sub_ovf checking
    ret int %%t
}
""" % locals())

extfunctions["%int_mul_ovf"] = (("%__prepare_OverflowError",), """
internal fastcc int %%int_mul_ovf(int %%x, int %%y) {
    %%t = mul int %%x, %%y
    %(int_ovf_test)s
return_block:
    ; XXX: TEST int_mul_ovf checking
    ret int %%t
}
""" % locals())


#binary with OverflowError and ValueError

extfunctions["%int_lshift_ovf_val"] = (("%__prepare_OverflowError","%__prepare_ValueError"), """
internal fastcc int %%int_lshift_ovf_val(int %%x, int %%y) {
    %%yu = cast int %%y to ubyte
    %%t = shl int %%x, ubyte %%yu
    %(int_ovf_test)s
return_block:
    ; XXX: TODO int_lshift_ovf_val checking VAL
    ret int %%t
}
""" % locals())


#binary with OverflowError and ZeroDivisionError

extfunctions["%int_floordiv_ovf_zer"] = (("%__prepare_OverflowError","%__prepare_ZeroDivisionError"), """
internal fastcc int %%int_floordiv_ovf_zer(int %%x, int %%y) {
    %(int_zer_test)s
    %%t = div int %%x, %%y
    %(int_ovf_test)s
return_block:
    ; XXX: TEST int_floordiv_ovf_zer checking
    ret int %%t
}
""" % locals())

extfunctions["%int_mod_ovf_zer"] = (("%__prepare_OverflowError","%__prepare_ZeroDivisionError"), """
internal fastcc int %%int_mod_ovf_zer(int %%x, int %%y) {
    %(int_zer_test)s
    %%t = rem int %%x, %%y
    %(int_ovf_test)s
return_block:
    ; XXX: TEST int_mod_ovf_zer checking
    ret int %%t
}
""" % locals())
