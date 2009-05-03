
from pypy.jit.backend.llvm.llvm_rffi import *


def test_from_llvm_py_example_1():
    # NOTE: no GC so far!!!!!!!!!

    # Create an (empty) module.
    my_module = LLVMModuleCreateWithName("my_module")

    # All the types involved here are "int"s. This type is represented
    # by an object of type LLVMTypeRef:
    ty_int = LLVMInt32Type()

    # We need to represent the class of functions that accept two integers
    # and return an integer. This is represented by another LLVMTypeRef:
    arglist = lltype.malloc(rffi.CArray(LLVMTypeRef), 2, flavor='raw')
    arglist[0] = ty_int
    arglist[1] = ty_int
    ty_func = LLVMFunctionType(ty_int, arglist, 2, False)
    lltype.free(arglist, flavor='raw')

    # Now we need a function named 'sum' of this type. Functions are not
    # free-standing; it needs to be contained in a module.
    f_sum = LLVMAddFunction(my_module, "sum", ty_func)
    f_arg_0 = LLVMGetParam(f_sum, 0)
    f_arg_1 = LLVMGetParam(f_sum, 1)

    # Our function needs a "basic block" -- a set of instructions that
    # end with a terminator (like return, branch etc.). By convention
    # the first block is called "entry".
    bb = LLVMAppendBasicBlock(f_sum, "entry")

    # Let's add instructions into the block. For this, we need an
    # instruction builder:
    builder = LLVMCreateBuilder()
    LLVMPositionBuilderAtEnd(builder, bb)

    # OK, now for the instructions themselves. We'll create an add
    # instruction that returns the sum as a value, which we'll use
    # a ret instruction to return.
    tmp = LLVMBuildAdd(builder, f_arg_0, f_arg_1, "tmp")
    LLVMBuildRet(builder, tmp)

    # We've completed the definition now! Let's see the LLVM assembly
    # language representation of what we've created: (it goes to stderr)
    LLVMDumpModule(my_module)
    return locals()


class LLVMException(Exception):
    pass


def test_from_llvm_py_example_2():
    d = test_from_llvm_py_example_1()
    my_module = d['my_module']
    ty_int = d['ty_int']
    f_sum = d['f_sum']

    # Create a module provider object first. Modules can come from
    # in-memory IRs like what we created now, or from bitcode (.bc)
    # files. The module provider abstracts this detail.
    mp = LLVMCreateModuleProviderForExistingModule(my_module)

    # Create an execution engine object. This creates a JIT compiler,
    # or complain on platforms that don't support it.
    ee_out = lltype.malloc(rffi.CArray(LLVMExecutionEngineRef), 1, flavor='raw')
    error_out = lltype.malloc(rffi.CArray(rffi.CCHARP), 1, flavor='raw')
    try:
        error = LLVMCreateJITCompiler(ee_out, mp, True, error_out)
        if rffi.cast(lltype.Signed, error) != 0:
            raise LLVMException(rffi.charp2str(error_out[0]))
        ee = ee_out[0]
    finally:
        lltype.free(error_out, flavor='raw')
        lltype.free(ee_out, flavor='raw')

    # The arguments needs to be passed as "GenericValue" objects.
    args = lltype.malloc(rffi.CArray(LLVMGenericValueRef), 2, flavor='raw')
    args[0] = LLVMCreateGenericValueOfInt(ty_int, 100, True)
    args[1] = LLVMCreateGenericValueOfInt(ty_int, 42, True)

    # Now let's compile and run!
    retval = LLVMRunFunction(ee, f_sum, 2, args)
    lltype.free(args, flavor='raw')

    # The return value is also GenericValue. Let's check it.
    ulonglong = LLVMGenericValueToInt(retval, True)
    res = rffi.cast(lltype.Signed, ulonglong)
    assert res == 142
