from rpython.flowspace.model import Variable, Constant, FSException
from rpython.rlib.unroll import SpecTag

def _copy(v):
    from rpython.flowspace.flowcontext import FlowSignal
    if isinstance(v, Variable):
        return Variable(v)
    elif isinstance(v, FlowSignal):
        vars = [_copy(var) for var in v.args]
        return v.rebuild(*vars)
    else:
        return v

def _union(seq1, seq2):
    return [union(v1, v2) for v1, v2 in zip(seq1, seq2)]


class FrameState(object):
    def __init__(self, locals_w, stack, last_exception, blocklist, next_offset):
        self.locals_w = locals_w
        self.stack = stack
        self.last_exception = last_exception
        self.blocklist = blocklist
        self.next_offset = next_offset

    @property
    def mergeable(self):
        data = self.locals_w + self.stack
        if self.last_exception is None:
            data.append(Constant(None))
            data.append(Constant(None))
        else:
            data.append(self.last_exception.w_type)
            data.append(self.last_exception.w_value)
        recursively_flatten(data)
        return data

    def copy(self):
        "Make a copy of this state in which all Variables are fresh."
        exc = self.last_exception
        if exc is not None:
            exc = FSException(_copy(exc.w_type), _copy(exc.w_value))
        return FrameState(map(_copy, self.locals_w), map(_copy, self.stack),
                exc, self.blocklist, self.next_offset)

    def getvariables(self):
        return [w for w in self.mergeable if isinstance(w, Variable)]

    def matches(self, other):
        """Two states match if they only differ by using different Variables
        at the same place"""
        # safety check, don't try to compare states with different
        # nonmergeable states
        assert self.blocklist == other.blocklist
        assert self.next_offset == other.next_offset
        for w1, w2 in zip(self.mergeable, other.mergeable):
            if not (w1 == w2 or (isinstance(w1, Variable) and
                                 isinstance(w2, Variable))):
                return False
        return True

    def union(self, other):
        """Compute a state that is at least as general as both self and other.
           A state 'a' is more general than a state 'b' if all Variables in 'b'
           are also Variables in 'a', but 'a' may have more Variables.
        """
        try:
            locals = _union(self.locals_w, other.locals_w)
            stack = _union(self.stack, other.stack)
            if self.last_exception is None:
                exc = other.last_exception
            elif other.last_exception is None:
                exc = self.last_exception
            else:
                e1 = self.last_exception
                e2 = other.last_exception
                exc = FSException(union(e1.w_type, e2.w_type),
                        union(e1.w_value, e2.w_value))
        except UnionError:
            return None
        return FrameState(locals, stack, exc, self.blocklist, self.next_offset)

    def getoutputargs(self, targetstate):
        "Return the output arguments needed to link self to targetstate."
        result = []
        for w_output, w_target in zip(self.mergeable, targetstate.mergeable):
            if isinstance(w_target, Variable):
                result.append(w_output)
        return result


class UnionError(Exception):
    "The two states should be merged."


def union(w1, w2):
    "Union of two variables or constants."
    from rpython.flowspace.flowcontext import FlowSignal
    if w1 == w2:
        return w1
    if w1 is None or w2 is None:
        return None  # if w1 or w2 is an undefined local, we "kill" the value
                     # coming from the other path and return an undefined local
    if isinstance(w1, Variable) or isinstance(w2, Variable):
        return Variable()  # new fresh Variable
    if isinstance(w1, Constant) and isinstance(w2, Constant):
        if isinstance(w1.value, SpecTag) or isinstance(w2.value, SpecTag):
            raise UnionError
        else:
            return Variable()  # generalize different constants
    if isinstance(w1, FlowSignal) and isinstance(w2, FlowSignal):
        if type(w1) is not type(w2):
            raise UnionError
        vars = [union(v1, v2) for v1, v2 in zip(w1.args, w2.args)]
        return w1.rebuild(*vars)
    if isinstance(w1, FlowSignal) or isinstance(w2, FlowSignal):
        raise UnionError
    raise TypeError('union of %r and %r' % (w1.__class__.__name__,
                                            w2.__class__.__name__))


# ____________________________________________________________
#
# We have to flatten out the state of the frame into a list of
# Variables and Constants.  This is done above by collecting the
# locals and the items on the value stack, but the latter may contain
# FlowSignal.  We have to handle these specially, because
# some of them hide references to more Variables and Constants.
# The trick is to flatten ("pickle") them into the list so that the
# extra Variables show up directly in the list too.

class PickleTag:
    pass

PICKLE_TAGS = {}
UNPICKLE_TAGS = {}


def recursively_flatten(lst):
    from rpython.flowspace.flowcontext import FlowSignal
    i = 0
    while i < len(lst):
        unroller = lst[i]
        if not isinstance(unroller, FlowSignal):
            i += 1
        else:
            vars = unroller.args
            key = unroller.__class__, len(vars)
            try:
                tag = PICKLE_TAGS[key]
            except KeyError:
                tag = PICKLE_TAGS[key] = Constant(PickleTag())
                UNPICKLE_TAGS[tag] = key
            lst[i:i + 1] = [tag] + vars


def recursively_unflatten(lst):
    for i in xrange(len(lst) - 1, -1, -1):
        item = lst[i]
        if item in UNPICKLE_TAGS:
            unrollerclass, argcount = UNPICKLE_TAGS[item]
            arguments = lst[i + 1:i + 1 + argcount]
            del lst[i + 1:i + 1 + argcount]
            unroller = unrollerclass.rebuild(*arguments)
            lst[i] = unroller
