import sys
from pypy.rpython.lltypesystem import lltype, rffi
from pypy.rlib import clibffi, jit


FFI_CIF = clibffi.FFI_CIFP.TO
FFI_TYPE = clibffi.FFI_TYPE_P.TO
FFI_TYPE_P = clibffi.FFI_TYPE_P
FFI_TYPE_PP = clibffi.FFI_TYPE_PP
FFI_ABI = clibffi.FFI_ABI
FFI_TYPE_STRUCT = clibffi.FFI_TYPE_STRUCT
SIZE_OF_FFI_ARG = rffi.sizeof(clibffi.ffi_arg)

# "cif_description" is a block of raw memory describing how to do the call.
# It starts with a block of memory of type FFI_CIF, which is used by libffi
# itself.  Following it, we find jit_libffi-specific information:
#
#  - 'exchange_size': an integer that tells how big a buffer we must
#    allocate for the call; this buffer should have enough room at the
#    beginning for an array of pointers to the actual argument values,
#    which is initialized internally by jit_ffi_call().
#
#  - 'exchange_result': the offset in that buffer for the result of the call.
#
#  - 'exchange_result_libffi': the actual offset passed to ffi_call().
#    Differs on big-endian machines if the result is an integer type smaller
#    than SIZE_OF_FFI_ARG (blame libffi).
#
#  - 'exchange_args[nargs]': the offset in that buffer for each argument.

CIF_DESCRIPTION = lltype.Struct(
    'CIF_DESCRIPTION',
    ('cif', FFI_CIF),
    ('abi', FFI_ABI),
    ('nargs', lltype.Signed),
    ('rtype', FFI_TYPE_P),
    ('atypes', FFI_TYPE_PP),
    ('exchange_size', lltype.Signed),
    ('exchange_result', lltype.Signed),
    ('exchange_result_libffi', lltype.Signed),
    ('exchange_args', lltype.Array(lltype.Signed,
                          hints={'nolength': True, 'immutable': True})),
    hints={'immutable': True})

CIF_DESCRIPTION_P = lltype.Ptr(CIF_DESCRIPTION)


@jit.oopspec("libffi_call(cif_description, func_addr, exchange_buffer)")
def jit_ffi_call(cif_description, func_addr, exchange_buffer):
    """Wrapper around ffi_call().  Must receive a CIF_DESCRIPTION_P that
    describes the layout of the 'exchange_buffer'.
    """
    buffer_array = rffi.cast(rffi.VOIDPP, exchange_buffer)
    for i in range(cif_description.nargs):
        data = rffi.ptradd(exchange_buffer, cif_description.exchange_args[i])
        buffer_array[i] = data
    resultdata = rffi.ptradd(exchange_buffer,
                             cif_description.exchange_result_libffi)
    clibffi.c_ffi_call(cif_description.cif, func_addr,
                       rffi.cast(rffi.VOIDP, resultdata),
                       buffer_array)

# ____________________________________________________________

class types(object):
    """
    This namespace contains the mapping the JIT needs from ffi types to
    a less strict "kind" character.
    """

    @classmethod
    def _import(cls):
        prefix = 'ffi_type_'
        for key, value in clibffi.__dict__.iteritems():
            if key.startswith(prefix):
                name = key[len(prefix):]
                setattr(cls, name, value)
        cls.slong = clibffi.cast_type_to_ffitype(rffi.LONG)
        cls.ulong = clibffi.cast_type_to_ffitype(rffi.ULONG)
        cls.slonglong = clibffi.cast_type_to_ffitype(rffi.LONGLONG)
        cls.ulonglong = clibffi.cast_type_to_ffitype(rffi.ULONGLONG)
        cls.signed = clibffi.cast_type_to_ffitype(rffi.SIGNED)
        cls.wchar_t = clibffi.cast_type_to_ffitype(lltype.UniChar)
        del cls._import

    @staticmethod
    @jit.elidable
    def getkind(ffi_type):
        """Returns 'v' for void, 'f' for float, 'i' for signed integer,
        'u' for unsigned integer, 'S' for singlefloat, 'L' for long long
        integer (signed or unsigned), or '*' for struct.
        """
        if   ffi_type == types.void:    return 'v'
        elif ffi_type == types.double:  return 'f'
        elif ffi_type == types.float:   return 'S'
        elif ffi_type == types.pointer: return 'i'
        #
        elif ffi_type == types.schar:   return 'i'
        elif ffi_type == types.uchar:   return 'u'
        elif ffi_type == types.sshort:  return 'i'
        elif ffi_type == types.ushort:  return 'u'
        elif ffi_type == types.sint:    return 'i'
        elif ffi_type == types.uint:    return 'u'
        elif ffi_type == types.slong:   return 'i'
        elif ffi_type == types.ulong:   return 'u'
        #
        elif ffi_type == types.sint8:   return 'i'
        elif ffi_type == types.uint8:   return 'u'
        elif ffi_type == types.sint16:  return 'i'
        elif ffi_type == types.uint16:  return 'u'
        elif ffi_type == types.sint32:  return 'i'
        elif ffi_type == types.uint32:  return 'u'
        ## (note that on 64-bit platforms, types.sint64 == types.slong and the
        ## case == caught above)
        elif ffi_type == types.sint64:  return 'L'
        elif ffi_type == types.uint64:  return 'L'
        #
        elif types.is_struct(ffi_type): return '*'
        raise KeyError

    @staticmethod
    @jit.elidable
    def is_struct(ffi_type):
        return rffi.getintfield(ffi_type, 'c_type') == FFI_TYPE_STRUCT

types._import()
