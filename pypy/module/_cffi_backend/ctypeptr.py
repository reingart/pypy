"""
Pointers.
"""

from pypy.interpreter.error import OperationError, operationerrfmt
from pypy.rpython.lltypesystem import lltype, rffi
from pypy.rlib.objectmodel import keepalive_until_here
from pypy.rlib.rarithmetic import ovfcheck

from pypy.module._cffi_backend.ctypeobj import W_CType
from pypy.module._cffi_backend import cdataobj, misc, ctypeprim


class W_CTypePtrOrArray(W_CType):
    _attrs_            = ['ctitem', 'can_cast_anything', 'is_struct_ptr',
                          'length']
    _immutable_fields_ = ['ctitem', 'can_cast_anything', 'is_struct_ptr',
                          'length']
    length = -1

    def __init__(self, space, size, extra, extra_position, ctitem,
                 could_cast_anything=True):
        from pypy.module._cffi_backend.ctypestruct import W_CTypeStructOrUnion
        name, name_position = ctitem.insert_name(extra, extra_position)
        W_CType.__init__(self, space, size, name, name_position)
        # this is the "underlying type":
        #  - for pointers, it is the pointed-to type
        #  - for arrays, it is the array item type
        #  - for functions, it is the return type
        self.ctitem = ctitem
        self.can_cast_anything = could_cast_anything and ctitem.cast_anything
        self.is_struct_ptr = isinstance(ctitem, W_CTypeStructOrUnion)

    def is_char_ptr_or_array(self):
        return isinstance(self.ctitem, ctypeprim.W_CTypePrimitiveChar)

    def is_unichar_ptr_or_array(self):
        return isinstance(self.ctitem, ctypeprim.W_CTypePrimitiveUniChar)

    def is_char_or_unichar_ptr_or_array(self):
        return isinstance(self.ctitem, ctypeprim.W_CTypePrimitiveCharOrUniChar)

    def cast(self, w_ob):
        # cast to a pointer, to a funcptr, or to an array.
        # Note that casting to an array is an extension to the C language,
        # which seems to be necessary in order to sanely get a
        # <cdata 'int[3]'> at some address.
        if self.size < 0:
            return W_CType.cast(self, w_ob)
        space = self.space
        ob = space.interpclass_w(w_ob)
        if (isinstance(ob, cdataobj.W_CData) and
                isinstance(ob.ctype, W_CTypePtrOrArray)):
            value = ob._cdata
        else:
            value = misc.as_unsigned_long(space, w_ob, strict=False)
            value = rffi.cast(rffi.CCHARP, value)
        return cdataobj.W_CData(space, value, self)

    def convert_array_from_object(self, cdata, w_ob):
        space = self.space
        if (space.isinstance_w(w_ob, space.w_list) or
            space.isinstance_w(w_ob, space.w_tuple)):
            lst_w = space.listview(w_ob)
            if self.length >= 0 and len(lst_w) > self.length:
                raise operationerrfmt(space.w_IndexError,
                    "too many initializers for '%s' (got %d)",
                                      self.name, len(lst_w))
            ctitem = self.ctitem
            for i in range(len(lst_w)):
                ctitem.convert_from_object(cdata, lst_w[i])
                cdata = rffi.ptradd(cdata, ctitem.size)
        elif (self.ctitem.is_primitive_integer and
              self.ctitem.size == rffi.sizeof(lltype.Char)):
            try:
                s = space.str_w(w_ob)
            except OperationError, e:
                if not e.match(space, space.w_TypeError):
                    raise
                raise self._convert_error("str or list or tuple", w_ob)
            n = len(s)
            if self.length >= 0 and n > self.length:
                raise operationerrfmt(space.w_IndexError,
                                      "initializer string is too long for '%s'"
                                      " (got %d characters)",
                                      self.name, n)
            for i in range(n):
                cdata[i] = s[i]
            if n != self.length:
                cdata[n] = '\x00'
        elif isinstance(self.ctitem, ctypeprim.W_CTypePrimitiveUniChar):
            try:
                s = space.unicode_w(w_ob)
            except OperationError, e:
                if not e.match(space, space.w_TypeError):
                    raise
                raise self._convert_error("unicode or list or tuple", w_ob)
            n = len(s)
            if self.length >= 0 and n > self.length:
                raise operationerrfmt(space.w_IndexError,
                              "initializer unicode string is too long for '%s'"
                                      " (got %d characters)",
                                      self.name, n)
            unichardata = rffi.cast(rffi.CWCHARP, cdata)
            for i in range(n):
                unichardata[i] = s[i]
            if n != self.length:
                unichardata[n] = u'\x00'
        else:
            raise self._convert_error("list or tuple", w_ob)

    def string(self, cdataobj, maxlen):
        space = self.space
        if isinstance(self.ctitem, ctypeprim.W_CTypePrimitive):
            cdata = cdataobj._cdata
            if not cdata:
                raise operationerrfmt(space.w_RuntimeError,
                                      "cannot use string() on %s",
                                      space.str_w(cdataobj.repr()))
            #
            from pypy.module._cffi_backend import ctypearray
            length = maxlen
            if length < 0 and isinstance(self, ctypearray.W_CTypeArray):
                length = cdataobj.get_array_length()
            #
            # pointer to a primitive type of size 1: builds and returns a str
            if self.ctitem.size == rffi.sizeof(lltype.Char):
                if length < 0:
                    s = rffi.charp2str(cdata)
                else:
                    s = rffi.charp2strn(cdata, length)
                keepalive_until_here(cdataobj)
                return space.wrap(s)
            #
            # pointer to a wchar_t: builds and returns a unicode
            if self.is_unichar_ptr_or_array():
                cdata = rffi.cast(rffi.CWCHARP, cdata)
                if length < 0:
                    u = rffi.wcharp2unicode(cdata)
                else:
                    u = rffi.wcharp2unicoden(cdata, length)
                keepalive_until_here(cdataobj)
                return space.wrap(u)
        #
        return W_CType.string(self, cdataobj, maxlen)


class W_CTypePtrBase(W_CTypePtrOrArray):
    # base class for both pointers and pointers-to-functions
    _attrs_ = []

    def convert_to_object(self, cdata):
        ptrdata = rffi.cast(rffi.CCHARPP, cdata)[0]
        return cdataobj.W_CData(self.space, ptrdata, self)

    def convert_from_object(self, cdata, w_ob):
        space = self.space
        ob = space.interpclass_w(w_ob)
        if not isinstance(ob, cdataobj.W_CData):
            raise self._convert_error("cdata pointer", w_ob)
        other = ob.ctype
        if not isinstance(other, W_CTypePtrBase):
            from pypy.module._cffi_backend import ctypearray
            if isinstance(other, ctypearray.W_CTypeArray):
                other = other.ctptr
            else:
                raise self._convert_error("compatible pointer", w_ob)
        if self is not other:
            if not (self.can_cast_anything or other.can_cast_anything):
                raise self._convert_error("compatible pointer", w_ob)

        rffi.cast(rffi.CCHARPP, cdata)[0] = ob._cdata

    def _alignof(self):
        from pypy.module._cffi_backend import newtype
        return newtype.alignment_of_pointer


class W_CTypePointer(W_CTypePtrBase):
    _attrs_ = []

    def __init__(self, space, ctitem):
        from pypy.module._cffi_backend import ctypearray
        size = rffi.sizeof(rffi.VOIDP)
        if isinstance(ctitem, ctypearray.W_CTypeArray):
            extra = "(*)"    # obscure case: see test_array_add
        else:
            extra = " *"
        W_CTypePtrBase.__init__(self, space, size, extra, 2, ctitem)

    def newp(self, w_init):
        space = self.space
        ctitem = self.ctitem
        datasize = ctitem.size
        if datasize < 0:
            raise operationerrfmt(space.w_TypeError,
                "cannot instantiate ctype '%s' of unknown size",
                                  self.name)
        if self.is_struct_ptr:
            # 'newp' on a struct-or-union pointer: in this case, we return
            # a W_CDataPtrToStruct object which has a strong reference
            # to a W_CDataNewOwning that really contains the structure.
            cdatastruct = cdataobj.W_CDataNewOwning(space, datasize, ctitem)
            cdata = cdataobj.W_CDataPtrToStructOrUnion(space,
                                                       cdatastruct._cdata,
                                                       self, cdatastruct)
        else:
            if self.is_char_or_unichar_ptr_or_array():
                datasize *= 2       # forcefully add a null character
            cdata = cdataobj.W_CDataNewOwning(space, datasize, self)
        #
        if not space.is_w(w_init, space.w_None):
            ctitem.convert_from_object(cdata._cdata, w_init)
            keepalive_until_here(cdata)
        return cdata

    def _check_subscript_index(self, w_cdata, i):
        if (isinstance(w_cdata, cdataobj.W_CDataNewOwning) or
            isinstance(w_cdata, cdataobj.W_CDataPtrToStructOrUnion)):
            if i != 0:
                space = self.space
                raise operationerrfmt(space.w_IndexError,
                                      "cdata '%s' can only be indexed by 0",
                                      self.name)
        return self

    def add(self, cdata, i):
        space = self.space
        ctitem = self.ctitem
        if ctitem.size < 0:
            raise operationerrfmt(space.w_TypeError,
                                  "ctype '%s' points to items of unknown size",
                                  self.name)
        p = rffi.ptradd(cdata, i * self.ctitem.size)
        return cdataobj.W_CData(space, p, self)

    def _prepare_pointer_call_argument(self, w_init):
        space = self.space
        if (space.isinstance_w(w_init, space.w_list) or
            space.isinstance_w(w_init, space.w_tuple)):
            length = space.int_w(space.len(w_init))
        elif space.isinstance_w(w_init, space.w_basestring):
            # from a string, we add the null terminator
            length = space.int_w(space.len(w_init)) + 1
        else:
            return lltype.nullptr(rffi.CCHARP.TO)
        if self.ctitem.size <= 0:
            return lltype.nullptr(rffi.CCHARP.TO)
        try:
            datasize = ovfcheck(length * self.ctitem.size)
        except OverflowError:
            raise OperationError(space.w_OverflowError,
                space.wrap("array size would overflow a ssize_t"))
        result = lltype.malloc(rffi.CCHARP.TO, datasize,
                               flavor='raw', zero=True)
        try:
            self.convert_array_from_object(result, w_init)
        except Exception:
            lltype.free(result, flavor='raw')
            raise
        return result

    def convert_argument_from_object(self, cdata, w_ob):
        from pypy.module._cffi_backend.ctypefunc import set_mustfree_flag
        space = self.space
        ob = space.interpclass_w(w_ob)
        if isinstance(ob, cdataobj.W_CData):
            buffer = lltype.nullptr(rffi.CCHARP.TO)
        else:
            buffer = self._prepare_pointer_call_argument(w_ob)
        #
        if buffer:
            rffi.cast(rffi.CCHARPP, cdata)[0] = buffer
            set_mustfree_flag(cdata, True)
            return True
        else:
            set_mustfree_flag(cdata, False)
            self.convert_from_object(cdata, w_ob)
            return False

    def getcfield(self, attr):
        return self.ctitem.getcfield(attr)

    def typeoffsetof(self, fieldname):
        if fieldname is None:
            return W_CTypePtrBase.typeoffsetof(self, fieldname)
        else:
            return self.ctitem.typeoffsetof(fieldname)

    def rawaddressof(self, cdata, offset):
        from pypy.module._cffi_backend.ctypestruct import W_CTypeStructOrUnion
        space = self.space
        ctype2 = cdata.ctype
        if (isinstance(ctype2, W_CTypeStructOrUnion) or
            (isinstance(ctype2, W_CTypePtrOrArray) and ctype2.is_struct_ptr)):
            ptrdata = rffi.ptradd(cdata._cdata, offset)
            return cdataobj.W_CData(space, ptrdata, self)
        else:
            raise OperationError(space.w_TypeError,
                     space.wrap("expected a 'cdata struct-or-union' object"))
