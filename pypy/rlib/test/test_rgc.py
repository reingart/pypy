from pypy.rpython.test.test_llinterp import gengraph, interpret
from pypy.rpython.lltypesystem import lltype
from pypy.rlib import rgc # Force registration of gc.collect
import gc
import py, sys

def test_collect():
    def f():
        return gc.collect()

    t, typer, graph = gengraph(f, [])
    ops = list(graph.iterblockops())
    assert len(ops) == 1
    op = ops[0][1]
    assert op.opname == 'gc__collect'
    assert len(op.args) == 0

    res = interpret(f, [])
    
    assert res is None

def test_collect_0():
    if sys.version_info < (2, 5):
        py.test.skip("requires Python 2.5 to call gc.collect() with an arg")

    def f():
        return gc.collect(0)

    t, typer, graph = gengraph(f, [])
    ops = list(graph.iterblockops())
    assert len(ops) == 1
    op = ops[0][1]
    assert op.opname == 'gc__collect'
    assert len(op.args) == 1    
    assert op.args[0].value == 0

    res = interpret(f, [])
    
    assert res is None    
    
def test_can_move():
    T0 = lltype.GcStruct('T')
    T1 = lltype.GcArray(lltype.Float)
    def f(i):
        if i:
            return rgc.can_move(lltype.malloc(T0))
        else:
            return rgc.can_move(lltype.malloc(T1, 1))

    t, typer, graph = gengraph(f, [int])
    ops = list(graph.iterblockops())
    res = [op for op in ops if op[1].opname == 'gc_can_move']
    assert len(res) == 2

    res = interpret(f, [1])
    
    assert res == True
    
def test_resizable_buffer():
    from pypy.rpython.lltypesystem.rstr import STR
    from pypy.rpython.annlowlevel import hlstr
    
    def f():
        ptr = rgc.resizable_buffer_of_shape(STR, 1)
        ptr.chars[0] = 'a'
        ptr = rgc.resize_buffer(ptr, 1, 2)
        ptr.chars[1] = 'b'
        return hlstr(rgc.finish_building_buffer(ptr, 2))

    assert f() == 'ab'

def test_ll_arraycopy_1():
    TYPE = lltype.GcArray(lltype.Signed)
    a1 = lltype.malloc(TYPE, 10)
    a2 = lltype.malloc(TYPE, 6)
    for i in range(10): a1[i] = 100 + i
    for i in range(6):  a2[i] = 200 + i
    rgc.ll_arraycopy(a1, a2, 4, 2, 3)
    for i in range(10):
        assert a1[i] == 100 + i
    for i in range(6):
        if 2 <= i < 5:
            assert a2[i] == a1[i+2]
        else:
            assert a2[i] == 200 + i

def test_ll_arraycopy_2():
    TYPE = lltype.GcArray(lltype.Void)
    a1 = lltype.malloc(TYPE, 10)
    a2 = lltype.malloc(TYPE, 6)
    rgc.ll_arraycopy(a1, a2, 4, 2, 3)
    # nothing to assert here, should not crash...

def test_ll_arraycopy_3():
    S = lltype.Struct('S')    # non-gc
    TYPE = lltype.GcArray(lltype.Ptr(S))
    a1 = lltype.malloc(TYPE, 10)
    a2 = lltype.malloc(TYPE, 6)
    org1 = [None] * 10
    org2 = [None] * 6
    for i in range(10): a1[i] = org1[i] = lltype.malloc(S, immortal=True)
    for i in range(6):  a2[i] = org2[i] = lltype.malloc(S, immortal=True)
    rgc.ll_arraycopy(a1, a2, 4, 2, 3)
    for i in range(10):
        assert a1[i] == org1[i]
    for i in range(6):
        if 2 <= i < 5:
            assert a2[i] == a1[i+2]
        else:
            assert a2[i] == org2[i]

def test_ll_arraycopy_4():
    S = lltype.GcStruct('S')
    TYPE = lltype.GcArray(lltype.Ptr(S))
    a1 = lltype.malloc(TYPE, 10)
    a2 = lltype.malloc(TYPE, 6)
    org1 = [None] * 10
    org2 = [None] * 6
    for i in range(10): a1[i] = org1[i] = lltype.malloc(S)
    for i in range(6):  a2[i] = org2[i] = lltype.malloc(S)
    rgc.ll_arraycopy(a1, a2, 4, 2, 3)
    for i in range(10):
        assert a1[i] == org1[i]
    for i in range(6):
        if 2 <= i < 5:
            assert a2[i] == a1[i+2]
        else:
            assert a2[i] == org2[i]
