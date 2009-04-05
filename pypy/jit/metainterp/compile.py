
from pypy.rpython.ootypesystem import ootype
from pypy.objspace.flow.model import Constant, Variable
from pypy.rlib.objectmodel import we_are_translated
from pypy.conftest import option

from pypy.jit.metainterp.resoperation import ResOperation, rop
from pypy.jit.metainterp.history import TreeLoop, log, Box, History
from pypy.jit.metainterp.history import AbstractDescr

def compile_new_loop(metainterp, old_loops, greenkey):
    """Try to compile a new loop by closing the current history back
    to the first operation.
    """
    if we_are_translated():
        return compile_fresh_loop(metainterp, old_loops, greenkey)
    else:
        return _compile_new_loop_1(metainterp, old_loops, greenkey)

def compile_new_bridge(metainterp, old_loops, resumekey):
    """Try to compile a new bridge leading from the beginning of the history
    to some existing place.
    """
    if we_are_translated():
        return compile_fresh_bridge(metainterp, old_loops, resumekey)
    else:
        return _compile_new_bridge_1(metainterp, old_loops, resumekey)

class BridgeInProgress(Exception):
    pass


# the following is not translatable
def _compile_new_loop_1(metainterp, old_loops, greenkey):
    old_loops_1 = old_loops[:]
    try:
        loop = compile_fresh_loop(metainterp, old_loops, greenkey)
    except Exception, exc:
        show_loop(metainterp, error=exc)
        raise
    else:
        if loop in old_loops_1:
            log.info("reusing loop at %r" % (loop,))
        else:
            show_loop(metainterp, loop)
    loop.check_consistency()
    return loop

def _compile_new_bridge_1(metainterp, old_loops, resumekey):
    try:
        target_loop = compile_fresh_bridge(metainterp, old_loops,
                                           resumekey)
    except Exception, exc:
        show_loop(metainterp, error=exc)
        raise
    else:
        if target_loop is not None:
            show_loop(metainterp, target_loop)
    if target_loop is not None:
        target_loop.check_consistency()
    return target_loop

def show_loop(metainterp, loop=None, error=None):
    # debugging
    if option.view:
        if error:
            errmsg = error.__class__.__name__
            if str(error):
                errmsg += ': ' + str(error)
        else:
            errmsg = None
        if loop is None:
            extraloops = []
        else:
            extraloops = [loop]
        metainterp.stats.view(errmsg=errmsg, extraloops=extraloops)

def create_empty_loop(metainterp):
    if we_are_translated():
        name = 'Loop'
    else:
        name = 'Loop #%d' % len(metainterp.stats.loops)
    return TreeLoop(name)

# ____________________________________________________________

def compile_fresh_loop(metainterp, old_loops, greenkey):
    history = metainterp.history
    loop = create_empty_loop(metainterp)
    loop.greenkey = greenkey
    loop.inputargs = history.inputargs
    loop.operations = history.operations
    loop.operations[-1].jump_target = loop
    old_loop = metainterp.optimize_loop(metainterp.options, old_loops,
                                        loop, metainterp.cpu)
    if old_loop is not None:
        return old_loop
    history.source_link = loop
    send_loop_to_backend(metainterp, loop, "loop")
    metainterp.stats.loops.append(loop)
    old_loops.append(loop)
    return loop

def send_loop_to_backend(metainterp, loop, type):
    metainterp.cpu.compile_operations(loop)
    if not we_are_translated():
        if type != "entry bridge":
            metainterp.stats.compiled_count += 1
        else:
            loop._ignore_during_counting = True
        log.info("compiled new " + type)

# ____________________________________________________________

class ResumeGuardDescr(AbstractDescr):
    def __init__(self, guard_op, resume_info, history, history_guard_index):
        self.resume_info = resume_info
        self.guard_op = guard_op
        self.counter = 0
        self.history = history
        assert history_guard_index >= 0
        self.history_guard_index = history_guard_index

    def get_guard_op(self):
        guard_op = self.guard_op
        if guard_op.optimized is not None:   # should always be the case,
            return guard_op.optimized        # except if not optimizing at all
        else:
            return guard_op

    def compile_and_attach(self, metainterp, new_loop):
        # We managed to create a bridge.  Attach the new operations
        # to the existing source_loop and recompile the whole thing.
        source_loop = self.find_source_loop()
        metainterp.history.source_link = self.history
        metainterp.history.source_guard_index = self.history_guard_index
        guard_op = self.get_guard_op()
        guard_op.suboperations = new_loop.operations
        send_loop_to_backend(metainterp, source_loop, "bridge")

    def find_source_loop(self):
        # Find the TreeLoop object that contains this guard operation.
        source_loop = self.history.source_link
        while not isinstance(source_loop, TreeLoop):
            source_loop = source_loop.source_link
        return source_loop

    def find_toplevel_history(self):
        # Find the History that describes the start of the loop containing this
        # guard operation.
        history = self.history
        prevhistory = history.source_link
        while isinstance(prevhistory, History):
            history = prevhistory
            prevhistory = history.source_link
        return history


class ResumeFromInterpDescr(AbstractDescr):
    def __init__(self, original_boxes):
        self.original_boxes = original_boxes

    def compile_and_attach(self, metainterp, new_loop):
        # We managed to create a bridge going from the interpreter
        # to previously-compiled code.  We keep 'new_loop', which is not
        # a loop at all but ends in a jump to the target loop.  It starts
        # with completely unoptimized arguments, as in the interpreter.
        num_green_args = metainterp.num_green_args
        greenkey = self.original_boxes[:num_green_args]
        redkey = self.original_boxes[num_green_args:]
        metainterp.history.source_link = new_loop
        metainterp.history.inputargs = redkey
        new_loop.greenkey = greenkey
        new_loop.inputargs = redkey
        send_loop_to_backend(metainterp, new_loop, "entry bridge")
        metainterp.stats.loops.append(new_loop)
        # send the new_loop to warmspot.py, to be called directly the next time
        metainterp.state.attach_unoptimized_bridge_from_interp(greenkey,
                                                               new_loop)


def compile_fresh_bridge(metainterp, old_loops, resumekey):
    # The history contains new operations to attach as the code for the
    # failure of 'resumekey.guard_op'.
    #
    # Attempt to use optimize_bridge().  This may return None in case
    # it does not work -- i.e. none of the existing old_loops match.
    new_loop = create_empty_loop(metainterp)
    new_loop.operations = metainterp.history.operations
    target_loop = metainterp.optimize_bridge(metainterp.options, old_loops,
                                             new_loop, metainterp.cpu)
    # Did it work?  If not, prepare_loop_from_bridge() will probably be used.
    if target_loop is not None:
        # Yes, we managed to create a bridge.  Dispatch to resumekey to
        # know exactly what we must do (ResumeGuardDescr/ResumeFromInterpDescr)
        op = new_loop.operations[-1]
        op.jump_target = target_loop
        resumekey.compile_and_attach(metainterp, new_loop)
    return target_loop


def prepare_loop_from_bridge(metainterp, resumekey):
    # To handle this case, we prepend to the history the unoptimized
    # operations coming from the loop, in order to make a (fake) complete
    # unoptimized trace.  (Then we will just compile this loop normally.)
    if not we_are_translated():
        log.info("completing the bridge into a stand-alone loop")
    operations = metainterp.history.operations
    metainterp.history.operations = []
    assert isinstance(resumekey, ResumeGuardDescr)
    append_full_operations(metainterp.history,
                           resumekey.history,
                           resumekey.history_guard_index)
    metainterp.history.operations.extend(operations)

def append_full_operations(history, sourcehistory, guard_index):
    prev = sourcehistory.source_link
    if isinstance(prev, History):
        append_full_operations(history, prev, sourcehistory.source_guard_index)
    history.operations.extend(sourcehistory.operations[:guard_index])
    op = inverse_guard(sourcehistory.operations[guard_index])
    history.operations.append(op)

def inverse_guard(guard_op):
    suboperations = guard_op.suboperations
    assert guard_op.is_guard()
    if guard_op.opnum == rop.GUARD_TRUE:
        guard_op = ResOperation(rop.GUARD_FALSE, guard_op.args, None)
    elif guard_op.opnum == rop.GUARD_FALSE:
        guard_op = ResOperation(rop.GUARD_TRUE, guard_op.args, None)
    else:
        # XXX other guards have no inverse so far
        raise InverseTheOtherGuardsPlease(guard_op)
    #
    guard_op.suboperations = suboperations
    return guard_op

class InverseTheOtherGuardsPlease(Exception):
    pass
