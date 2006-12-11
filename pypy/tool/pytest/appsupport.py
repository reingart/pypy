from __future__ import generators 
import autopath
import py
from py.__.magic import exprinfo
from pypy.interpreter import gateway
from pypy.interpreter.error import OperationError

# ____________________________________________________________

class AppCode(object):
    def __init__(self, space, pycode):
        self.code = space.unwrap(space.getattr(pycode, space.wrap('co_code')))
        self.w_file = space.getattr(pycode, space.wrap('co_filename'))
        self.firstlineno = space.unwrap(space.getattr(pycode, space.wrap('co_firstlineno')))
        #try:
        #    self.path = space.unwrap(space.getattr(self.w_file, space.wrap('__path__')))
        #except OperationError:
        #    self.path = space.unwrap(space.getattr(
        self.path = py.path.local(space.str_w(self.w_file))
    
    def fullsource(self):
        return py.code.Source(self.path.read(mode="rU"))
    fullsource = property(fullsource, None, None, "Full source of AppCode")

class AppFrame(py.code.Frame):

    def __init__(self, space, pyframe):
        self.code = AppCode(space, \
            space.unwrap(space.getattr(pyframe, space.wrap('f_code'))))
        #self.code = py.code.Code(pyframe.pycode)
        self.lineno = space.unwrap(space.getattr(pyframe, space.wrap('f_lineno'))) - 1
        #pyframe.get_last_lineno() - 1
        self.space = space
        self.w_globals = space.getattr(pyframe, space.wrap('f_globals'))
        self.w_locals = space.getattr(pyframe, space.wrap('f_locals'))
        self.f_locals = self.w_locals   # for py.test's recursion detection

    def eval(self, code, **vars):
        space = self.space
        for key, w_value in vars.items():
            space.setitem(self.w_locals, space.wrap(key), w_value)
        return space.eval(code, self.w_globals, self.w_locals)

    def exec_(self, code, **vars):
        space = self.space
        for key, w_value in vars.items():
            space.setitem(self.w_locals, space.wrap(key), w_value)
        space.exec_(code, self.w_globals, self.w_locals)

    def repr(self, w_value):
        return self.space.unwrap(self.space.repr(w_value))

    def is_true(self, w_value):
        return self.space.is_true(w_value)

class AppExceptionInfo(py.code.ExceptionInfo):
    """An ExceptionInfo object representing an app-level exception."""

    def __init__(self, space, operr):
        self.space = space
        self.operr = operr
        self.traceback = AppTraceback(space, self.operr.application_traceback)

    def exconly(self, tryshort=True): 
        return '(application-level) ' + self.operr.errorstr(self.space)

    def errisinstance(self, exc): 
        clsname = exc.__name__ 
        try: 
            w_exc = getattr(self.space, 'w_' + clsname) 
        except KeyboardInterrupt: 
            raise 
        except: 
            pass 
        else: 
            return self.operr.match(self.space, w_exc) 
        return False 

    def __str__(self):
        return '(application-level) ' + self.operr.errorstr(self.space)

class AppTracebackEntry(py.code.Traceback.Entry):
    exprinfo = None

    def __init__(self, space, tb):
        self.frame = AppFrame(space, space.getattr(tb, space.wrap('tb_frame')))
        self.lineno = space.unwrap(space.getattr(tb, space.wrap('tb_lineno'))) - 1

    def reinterpret(self):
        # XXX we need to solve a general problem: how to prevent
        #     reinterpretation from generating a different exception?
        #     This problem includes the fact that exprinfo will generate
        #     its own long message that looks like
        #        OperationError:   << [<W_TypeObject(NameError)>: W_StringObj...
        #     which is much less nice than the one produced by str(self).
        # XXX this reinterpret() is only here to prevent reinterpretation.
        return self.exprinfo

class AppTraceback(py.code.Traceback): 
    Entry = AppTracebackEntry 

    def __init__(self, space, apptb):
        l = []
        while apptb is not space.w_None: 
            l.append(self.Entry(space, apptb))
            apptb = space.getattr(apptb, space.wrap('tb_next'))
        list.__init__(self, l)
    
# ____________________________________________________________

def build_pytest_assertion(space):
    def my_init(space, w_self, __args__):
        "Our new AssertionError.__init__()."
        w_parent_init = space.getattr(w_BuiltinAssertionError,
                                      space.wrap('__init__'))
        space.call_args(w_parent_init, __args__.prepend(w_self))
        framestack = space.getexecutioncontext().framestack
##        # Argh! we may see app-level helpers in the frame stack!
##        #       that's very probably very bad...
##        if frame.code.co_name == 'normalize_exception': 
##            frame = framestack.top(1)
        
        # if the assertion provided a message, don't do magic
        args_w, kwargs_w = __args__.unpack()
        if args_w: 
            w_msg = args_w[0]
        else:
            frame = framestack.top(0)
            runner = AppFrame(space, frame)
            try:
                source = runner.statement
                source = str(source).strip()
            except py.error.ENOENT: 
                source = None
            from pypy import conftest
            if source and not conftest.option.nomagic: 
                msg = exprinfo.interpret(source, runner, should_fail=True)
                space.setattr(w_self, space.wrap('args'),
                            space.newtuple([space.wrap(msg)]))
                w_msg = space.wrap(msg)
            else:
                w_msg = space.w_None
        space.setattr(w_self, space.wrap('msg'), w_msg)

    # build a new AssertionError class to replace the original one.
    w_BuiltinAssertionError = space.getitem(space.builtin.w_dict, 
                                            space.wrap('AssertionError'))
    w_metaclass = space.type(w_BuiltinAssertionError)
    w_init = space.wrap(gateway.interp2app_temp(my_init,
                                                unwrap_spec=[gateway.ObjSpace,
                                                             gateway.W_Root,
                                                             gateway.Arguments]))
    w_dict = space.newdict()
    space.setitem(w_dict, space.wrap('__init__'), w_init)
    return space.call_function(w_metaclass,
                               space.wrap('AssertionError'),
                               space.newtuple([w_BuiltinAssertionError]),
                               w_dict)

def pypyraises(space, w_ExpectedException, w_expr, __args__):
    """A built-in function providing the equivalent of py.test.raises()."""
    args_w, kwds_w = __args__.unpack()
    if space.is_true(space.isinstance(w_expr, space.w_str)):
        if args_w:
            raise OperationError(space.w_TypeError,
                                 space.wrap("raises() takes no argument "
                                            "after a string expression"))
        expr = space.unwrap(w_expr)
        source = py.code.Source(expr)
        frame = space.getexecutioncontext().framestack.top()
        w_locals = frame.getdictscope()
        w_locals = space.call_method(w_locals, 'copy')
        for key, w_value in kwds_w.items():
            space.setitem(w_locals, space.wrap(key), w_value)
        try:
            space.exec_(str(source), frame.w_globals, w_locals)
        except OperationError, e:
            if e.match(space, w_ExpectedException):
                return space.sys.call('exc_info')
            raise
    else:
        try:
            space.call_args(w_expr, __args__)
        except OperationError, e:
            if e.match(space, w_ExpectedException):
                return space.sys.call('exc_info')
            raise
    raise OperationError(space.w_AssertionError,
                         space.wrap("DID NOT RAISE"))

app_raises = gateway.interp2app_temp(pypyraises,
                                     unwrap_spec=[gateway.ObjSpace,
                                                  gateway.W_Root,
                                                  gateway.W_Root,
                                                  gateway.Arguments])

def pypyskip(space, w_message): 
    """skip a test at app-level. """ 
    msg = space.unwrap(w_message) 
    py.test.skip(msg)

app_skip = gateway.interp2app_temp(pypyskip)

def raises_w(space, w_ExpectedException, *args, **kwds):
    try:
        excinfo = py.test.raises(OperationError, *args, **kwds)
        type, value, tb = excinfo._excinfo
        if not value.match(space, w_ExpectedException):
            raise type, value, tb
        return excinfo
    except py.test.Item.ExceptionFailure, e:
        e.tbindex = getattr(e, 'tbindex', -1) - 1
        raise

def eq_w(space, w_obj1, w_obj2): 
    """ return interp-level boolean of eq(w_obj1, w_obj2). """ 
    return space.is_true(space.eq(w_obj1, w_obj2))
