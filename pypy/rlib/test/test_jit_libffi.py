import math
import ctypes
from pypy.rpython.lltypesystem import lltype, rffi
from pypy.rlib import clibffi
from pypy.rlib.rarithmetic import intmask
from pypy.rlib.jit_libffi import CIF_DESCRIPTION
from pypy.rlib.jit_libffi import jit_ffi_prep_cif, jit_ffi_call


math_sin = intmask(ctypes.cast(ctypes.CDLL(None).sin, ctypes.c_void_p).value)
math_sin = rffi.cast(rffi.VOIDP, math_sin)


def test_jit_ffi_call():
    cd = lltype.malloc(CIF_DESCRIPTION, 1, flavor='raw')
    cd.abi = clibffi.FFI_DEFAULT_ABI
    cd.nargs = 1
    cd.rtype = clibffi.cast_type_to_ffitype(rffi.DOUBLE)
    atypes = lltype.malloc(clibffi.FFI_TYPE_PP.TO, 1, flavor='raw')
    atypes[0] = clibffi.cast_type_to_ffitype(rffi.DOUBLE)
    cd.atypes = atypes
    cd.exchange_size = 64    # 64 bytes of exchange data
    cd.exchange_result = 24
    cd.exchange_result_libffi = 24
    cd.exchange_args[0] = 16
    #
    jit_ffi_prep_cif(cd)
    #
    assert rffi.sizeof(rffi.DOUBLE) == 8
    exb = lltype.malloc(rffi.DOUBLEP.TO, 8, flavor='raw')
    exb[2] = 1.23
    jit_ffi_call(cd, math_sin, rffi.cast(rffi.CCHARP, exb))
    res = exb[3]
    lltype.free(exb, flavor='raw')
    #
    lltype.free(atypes, flavor='raw')
    lltype.free(cd, flavor='raw')
    #
    assert res == math.sin(1.23)
