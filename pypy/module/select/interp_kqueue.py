from pypy.interpreter.baseobjspace import Wrappable
from pypy.interpreter.error import OperationError, exception_from_errno
from pypy.interpreter.gateway import interp2app, unwrap_spec
from pypy.interpreter.typedef import TypeDef, generic_new_descr, GetSetProperty
from pypy.rlib._rsocket_rffi import socketclose
from pypy.rpython.lltypesystem import rffi, lltype
from pypy.rpython.tool import rffi_platform
from pypy.translator.tool.cbuild import ExternalCompilationInfo


eci = ExternalCompilationInfo(
    includes = ["sys/event.h"],
)


class CConfig:
    _compilation_info_ = eci

CConfig.kevent = rffi_platform.Struct("struct kevent", [
    ("ident", rffi.UINT),
    ("filter", rffi.INT),
    ("flags", rffi.UINT),
    ("fflags", rffi.UINT),
    ("data", rffi.INT),
    ("udata", rffi.VOIDP),
])

for symbol in ["EVFILT_READ", "EVFILT_WRITE", "EV_ADD", "EV_ONESHOT", "EV_ENABLE"]:
    setattr(CConfig, symbol, rffi_platform.DefinedConstantInteger(symbol))

cconfig = rffi_platform.configure(CConfig)

kevent = cconfig["kevent"]
KQ_FILTER_READ = cconfig["EVFILT_READ"]
KQ_FILTER_WRITE = cconfig["EVFILT_WRITE"]
KQ_EV_ADD = cconfig["EV_ADD"]
KQ_EV_ONESHOT = cconfig["EV_ONESHOT"]
KQ_EV_ENABLE = cconfig["EV_ENABLE"]

kqueue = rffi.llexternal("kqueue",
    [],
    rffi.INT,
    compilation_info=eci
)
    


class W_Kqueue(Wrappable):
    def __init__(self, space, kqfd):
        self.kqfd = kqfd

    def descr__new__(space, w_subtype):
        kqfd = kqueue()
        if kqfd < 0:
            raise exception_from_errno(space, space.w_IOError)
        return space.wrap(W_Kqueue(space, kqfd))

    @unwrap_spec(fd=int)
    def descr_fromfd(space, w_cls, fd):
        return space.wrap(W_Kqueue(space, fd))

    def __del__(self):
        self.close()

    def get_closed(self):
        return self.kqfd < 0

    def close(self):
        if not self.get_closed():
            socketclose(self.kqfd)
            self.kqfd = -1

    def check_closed(self, space):
        if self.get_closed():
            raise OperationError(space.w_ValueError, space.wrap("I/O operation on closed kqueue fd"))

    def descr_get_closed(self, space):
        return space.wrap(self.get_closed())

    def descr_fileno(self, space):
        self.check_closed(space)
        return space.wrap(self.kqfd)

    def descr_close(self, space):
        self.close()

    @unwrap_spec(max_events=int)
    def descr_control(self, space, w_changelist, max_events, w_timeout=None):
        self.check_closed(space)

        if max_events < 0:
            raise operationerrfmt(space.w_ValueError,
                "Length of eventlist must be 0 or positive, got %d", max_events
            )

        if space.is_w(w_timeout, space.w_None):
            timeoutspec = 
        


W_Kqueue.typedef = TypeDef("select.kqueue",
    __new__ = interp2app(W_Kqueue.descr__new__.im_func),
    fromfd = interp2app(W_Kqueue.descr_fromfd.im_func, as_classmethod=True),

    closed = GetSetProperty(W_Kqueue.descr_get_closed),
    fileno = interp2app(W_Kqueue.descr_fileno),

    close = interp2app(W_Kqueue.descr_close),
    control = interp2app(W_Kqueue.descr_control),
)
W_Kqueue.typedef.acceptable_as_base_class = False


class W_Kevent(Wrappable):
    def __init__(self, space):
        self.event = lltype.nullptr(kevent)

    def __del__(self):
        if self.event:
            lltype.free(self.event, flavor="raw")

    @unwrap_spec(filter=int, flags=int, fflags=int, data=int, udata=int)
    def descr__init__(self, space, w_ident, filter=KQ_FILTER_READ, flags=KQ_EV_ADD, fflags=0, data=0, udata=0):
        ident = space.c_filedescriptor_w(w_ident)
        
        self.event = lltype.malloc(kevent, flavor="raw")
        rffi.setintfield(self.event, "c_ident", ident)
        rffi.setintfield(self.event, "c_filter", filter)
        rffi.setintfield(self.event, "c_flags", flags)
        rffi.setintfield(self.event, "c_fflags", fflags)
        rffi.setintfield(self.event, "c_data", data)
        self.event.c_udata = rffi.cast(rffi.VOIDP, udata)

    def _compare_all_fields(self, other, op):
        for field in ["ident", "filter", "flags", "fflags", "data", "udata"]:
            lhs = getattr(self.event, "c_%s" % field)
            rhs = getattr(other.event, "c_%s" % field)
            if op == "eq":
                if lhs != rhs:
                    return False
            elif op == "lt":
                if lhs < rhs:
                    return True
            elif op == "ge":
                if lhs >= rhs:
                    return True
            else:
                assert False

        if op == "eq":
            return True
        elif op == "lt":
            return False
        elif op == "ge":
            return False

    def compare_all_fields(self, space, other, op):
        if not space.interp_w(W_Kevent, other):
            return space.w_NotImplemented
        return space.wrap(self._compare_all_fields(other, op))

    def descr__eq__(self, space, w_other):
        return self.compare_all_fields(space, w_other, "eq")

    def descr__lt__(self, space, w_other):
        return self.compare_all_fields(space, w_other, "lt")

    def descr__ge__(self, space, w_other):
        return self.compare_all_fields(space, w_other, "ge")

    def descr_get_ident(self, space):
        return space.wrap(self.event.c_ident)

    def descr_get_filter(self, space):
        return space.wrap(self.event.c_filter)

    def descr_get_flags(self, space):
        return space.wrap(self.event.c_flags)

    def descr_get_fflags(self, space):
        return space.wrap(self.event.c_fflags)

    def descr_get_data(self, space):
        return space.wrap(self.event.c_data)

    def descr_get_udata(self, space):
        return space.wrap(rffi.cast(rffi.INT, self.event.c_udata))


W_Kevent.typedef = TypeDef("select.kevent",
    __new__ = generic_new_descr(W_Kevent),
    __init__ = interp2app(W_Kevent.descr__init__),
    __eq__ = interp2app(W_Kevent.descr__eq__),
    __lt__ = interp2app(W_Kevent.descr__lt__),
    __ge__ = interp2app(W_Kevent.descr__ge__),

    ident = GetSetProperty(W_Kevent.descr_get_ident),
    filter = GetSetProperty(W_Kevent.descr_get_filter),
    flags = GetSetProperty(W_Kevent.descr_get_flags),
    fflags = GetSetProperty(W_Kevent.descr_get_fflags),
    data = GetSetProperty(W_Kevent.descr_get_data),
    udata = GetSetProperty(W_Kevent.descr_get_udata),
)
W_Kevent.typedef.acceptable_as_base_class = False
