from pypy.interpreter.typedef import (
    TypeDef, generic_new_descr)
from pypy.interpreter.gateway import interp2app, unwrap_spec
from pypy.interpreter.baseobjspace import ObjSpace, W_Root
from pypy.interpreter.error import OperationError, operationerrfmt
from pypy.rlib.rarithmetic import r_longlong
from pypy.module._io.interp_bufferedio import W_BufferedIOBase
from pypy.module._io.interp_iobase import convert_size
import sys

def buffer2string(buffer, start, end):
    from pypy.rlib.rstring import StringBuilder
    builder = StringBuilder(end - start)
    for i in range(start, end):
        builder.append(buffer[i])
    return builder.build()

class W_BytesIO(W_BufferedIOBase):
    def __init__(self, space):
        W_BufferedIOBase.__init__(self, space)
        self.pos = 0
        self.string_size = 0
        self.buf = []

    @unwrap_spec('self', ObjSpace, W_Root)
    def descr_init(self, space, w_initvalue=None):
        # In case __init__ is called multiple times
        self.string_size = 0
        self.pos = 0

        if not space.is_w(w_initvalue, space.w_None):
            self.write_w(space, w_initvalue)
            self.pos = 0

    @unwrap_spec('self', ObjSpace, W_Root)
    def read_w(self, space, w_size=None):
        self._check_closed(space)
        size = convert_size(space, w_size)

        # adjust invalid sizes
        available = self.string_size - self.pos
        if not 0 <= size <= available:
            size = available
            if size < 0:
                size = 0

        output = buffer2string(self.buf, self.pos, self.pos + size)
        self.pos += size
        return space.wrap(output)

    @unwrap_spec('self', ObjSpace, W_Root)
    def write_w(self, space, w_data):
        self._check_closed(space)
        buf = space.buffer_w(w_data)
        length = buf.getlength()
        if length == 0:
            return

        if self.pos + length > len(self.buf):
            self.buf.extend(['\0'] * (self.pos + length - len(self.buf)))

        if self.pos > self.string_size:
            # In case of overseek, pad with null bytes the buffer region
            # between the end of stream and the current position.
            #
            # 0   lo      string_size                           hi
            # |   |<---used--->|<----------available----------->|
            # |   |            <--to pad-->|<---to write--->    |
            # 0   buf                   position
            for i in range(self.string_size, self.pos):
                self.buf[i] = '\0'

        # Copy the data to the internal buffer, overwriting some of the
        # existing data if self->pos < self->string_size.
        for i in range(length):
            self.buf[self.pos + i] = buf.getitem(i)
        self.pos += length

        # Set the new length of the internal string if it has changed
        if self.string_size < self.pos:
            self.string_size = self.pos

        return space.wrap(length)

    @unwrap_spec('self', ObjSpace)
    def getvalue_w(self, space):
        self._check_closed(space)
        return space.wrap(buffer2string(self.buf, 0, self.string_size))

    @unwrap_spec('self', ObjSpace)
    def tell_w(self, space):
        self._check_closed(space)
        return space.wrap(self.pos)

    @unwrap_spec('self', ObjSpace, r_longlong, int)
    def seek_w(self, space, pos, whence=0):
        self._check_closed(space)

        if whence == 0:
            if pos < 0:
                raise OperationError(space.w_ValueError, space.wrap(
                    "negative seek value"))
        elif whence == 1:
            if pos > sys.maxint - self.pos:
                raise OperationError(space.w_OverflowError, space.wrap(
                    "new position too large"))
            pos += self.pos
        elif whence == 2:
            if pos > sys.maxint - self.string_size:
                raise OperationError(space.w_OverflowError, space.wrap(
                    "new position too large"))
            pos += self.string_size
        else:
            raise operationerrfmt(space.w_ValueError,
                "whence must be between 0 and 2, not %d", whence)

        if pos >= 0:
            self.pos = pos
        else:
            self.pos = 0
        return space.wrap(self.pos)

    @unwrap_spec('self', ObjSpace)
    def readable_w(self, space):
        return space.w_True

    @unwrap_spec('self', ObjSpace)
    def writable_w(self, space):
        return space.w_True

    @unwrap_spec('self', ObjSpace)
    def seekable_w(self, space):
        return space.w_True

W_BytesIO.typedef = TypeDef(
    'BytesIO', W_BufferedIOBase.typedef,
    __new__ = generic_new_descr(W_BytesIO),
    __init__  = interp2app(W_BytesIO.descr_init),

    read = interp2app(W_BytesIO.read_w),
    write = interp2app(W_BytesIO.write_w),
    getvalue = interp2app(W_BytesIO.getvalue_w),
    seek = interp2app(W_BytesIO.seek_w),
    tell = interp2app(W_BytesIO.tell_w),
    readable = interp2app(W_BytesIO.readable_w),
    writable = interp2app(W_BytesIO.writable_w),
    seekable = interp2app(W_BytesIO.seekable_w),
    )

