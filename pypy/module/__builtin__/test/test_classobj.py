
class AppTestOldstyle(object):
    def setup_class(cls):
        from pypy.conftest import gettestobjspace
        cls.space = gettestobjspace(**{"objspace.std.oldstyle": True})

    def test_simple(self):
        class A:
            a = 1
        assert A.__name__ == 'A'
        assert A.__bases__ == ()
        assert A.a == 1
        assert A.__dict__['a'] == 1
        a = A()
        a.b = 2
        assert a.b == 2
        assert a.a == 1
        assert a.__class__ is A
        assert a.__dict__ == {'b': 2}

    def test_mutate_class_special(self):
        class A:
            a = 1
        A.__name__ = 'B'
        assert A.__name__ == 'B'
        assert A.a == 1
        A.__dict__ = {'a': 5}
        assert A.a == 5
        class B:
            a = 17
            b = 18
        class C(A):
            c = 19
        assert C.a == 5
        assert C.c == 19
        C.__bases__ = (B, )
        assert C.a == 17
        assert C.b == 18
        assert C.c == 19
        C.__bases__ = (B, A)
        assert C.a == 17
        assert C.b == 18
        assert C.c == 19
        C.__bases__ = (A, B)
        assert C.a == 5
        assert C.b == 18
        assert C.c == 19

    def test_class_repr(self):
        class A:
            pass
        assert repr(A).startswith("<class __builtin__.A at 0x")
        A.__name__ = 'B'
        assert repr(A).startswith("<class __builtin__.B at 0x")
        A.__module__ = 'foo'
        assert repr(A).startswith("<class foo.B at 0x")
        A.__module__ = None
        assert repr(A).startswith("<class ?.B at 0x")
        del A.__module__
        assert repr(A).startswith("<class ?.B at 0x")

    def test_class_str(self):
        class A:
            pass
        assert str(A) == "__builtin__.A"
        A.__name__ = 'B'
        assert str(A) == "__builtin__.B"
        A.__module__ = 'foo'
        assert str(A) == "foo.B"
        A.__module__ = None
        assert str(A) == "B"
        del A.__module__
        assert str(A) == "B"

    def test_del_error_class_special(self):
        class A:
            a = 1
        raises(TypeError, "del A.__name__")
        raises(TypeError, "del A.__dict__")
        raises(TypeError, "del A.__bases__")

    def test_mutate_instance_special(self):
        class A:
            a = 1
        class B:
            a = 17
            b = 18
        a = A()
        assert isinstance(a, A)
        a.__class__ = B
        assert isinstance(a, B)
        assert a.a == 17
        assert a.b == 18


    def test_init(self):
        class A:
            a = 1
            def __init__(self, a):
                self.a = a
        a = A(2)
        assert a.a == 2
        class B:
            def __init__(self, a):
                return a

        raises(TypeError, B, 2)

    def test_method(self):
        class A:
            a = 1
            def f(self, a):
                return self.a + a
        a = A()
        assert a.f(2) == 3
        assert A.f(a, 2) == 3
        a.a = 5
        assert A.f(a, 2) == 7

    def test_inheritance(self):
        class A:
            a = 1
            b = 2
            def af(self):
                return 1
            def bf(self):
                return 2
        assert A.a == 1
        assert A.b == 2
        a = A()
        assert a.a == 1
        assert a.b == 2
        assert a.af() == 1
        assert a.bf() == 2
        assert A.af(a) == 1
        assert A.bf(a) == 2

        class B(A):
            a = 3
            c = 4
            def af(self):
                return 3
            def cf(self):
                return 4
        assert B.__bases__ == (A, )
        assert B.a == 3
        assert B.b == 2
        assert B.c == 4
        b = B()
        assert b.a == 3
        assert b.b == 2
        assert b.c == 4
        assert b.af() == 3
        assert b.bf() == 2
        assert b.cf() == 4
        assert B.af(b) == 3
        assert B.bf(b) == 2
        assert B.cf(b) == 4

    def test_inheritance_unbound_method(self):
        class A:
            def f(self):
                return 1
        raises(TypeError, A.f, 1)
        assert A.f(A()) == 1
        class B(A):
            pass
        raises(TypeError, B.f, 1)
        raises(TypeError, B.f, A())
        assert B.f(B()) == 1

    def test_len_getsetdelitem(self):
        class A:
            pass
        a = A()
        raises(AttributeError, len, a)
        raises(AttributeError, "a[5]")
        raises(AttributeError, "a[5] = 5")
        raises(AttributeError, "del a[5]")
        class A:
            def __init__(self):
                self.list = [1, 2, 3, 4, 5]
            def __len__(self):
                return len(self.list)
            def __getitem__(self, i):
                return self.list[i]
            def __setitem__(self, i, v):
                self.list[i] = v
            def __delitem__(self, i):
                del self.list[i]

        a = A()
        assert len(a) == 5
        del a[0]
        assert len(a) == 4
        assert a[0] == 2
        a[0] = 5
        assert a[0] == 5
        assert a
        assert bool(a) == True
        del a[0]
        del a[0]
        del a[0]
        del a[0]
        assert len(a) == 0
        assert not a
        assert bool(a) == False
        a = A()
        assert a[1:3] == [2, 3]
        a[1:3] = [1, 2, 3]
        assert a.list == [1, 1, 2, 3, 4, 5]
        del a[1:4]
        assert a.list == [1, 4, 5]

    def test_len_errors(self):
        class A:
            def __len__(self):
                return long(10)
        raises(TypeError, len, A())
        class A:
            def __len__(self):
                return -1
        raises(ValueError, len, A())

    def test_call(self):
        class A:
            pass
        a = A()
        raises(AttributeError, a)
        class A:
            def __call__(self, a, b):
                return a + b
        a = A()
        assert a(1, 2) == 3

    def test_nonzero(self):
        class A:
            pass
        a = A()
        assert a
        assert bool(a) == True
        class A:
            def __init__(self, truth):
                self.truth = truth
            def __nonzero__(self):
                return self.truth
        a = A(1)
        assert a
        assert bool(a) == True
        a = A(42)
        assert a
        assert bool(a) == True
        a = A(True)
        assert a
        assert bool(a) == True
        a = A(False)
        assert not a
        assert bool(a) == False
        a = A(0)
        assert not a
        assert bool(a) == False
        a = A(-1)
        raises(ValueError, "assert a")
        a = A("hello")
        raises(TypeError, "assert a")

    def test_repr(self):
        class A:
            pass
        a = A()
        assert repr(a).startswith("<__builtin__.A instance at")
        assert str(a).startswith("<__builtin__.A instance at")
        A.__name__ = "Foo"
        assert repr(a).startswith("<__builtin__.Foo instance at")
        assert str(a).startswith("<__builtin__.Foo instance at")
        A.__module__ = "bar"
        assert repr(a).startswith("<bar.Foo instance at")
        assert str(a).startswith("<bar.Foo instance at")
        A.__module__ = None
        assert repr(a).startswith("<?.Foo instance at")
        assert str(a).startswith("<?.Foo instance at")
        del A.__module__
        assert repr(a).startswith("<?.Foo instance at")
        assert str(a).startswith("<?.Foo instance at")
        class A:
            def __repr__(self):
                return "foo"
        assert repr(A()) == "foo"
        assert str(A()) == "foo"

    def test_str(self):
        class A:
            def __str__(self):
                return "foo"
        a = A()
        assert repr(a).startswith("<__builtin__.A instance at")
        assert str(a) == "foo"

    def test_iter(self):
        class A:
            def __init__(self):
                self.list = [1, 2, 3, 4, 5]
            def __iter__(self):
                return iter(self.list)
        for i, element in enumerate(A()):
            assert i + 1 == element
        class A:
            def __init__(self):
                self.list = [1, 2, 3, 4, 5]
            def __len__(self):
                return len(self.list)
            def __getitem__(self, i):
                return self.list[i]
        for i, element in enumerate(A()):
            assert i + 1 == element

    def test_getsetdelattr(self):
        class A:
            a = 1
            def __getattr__(self, attr):
                return attr.upper()
        a = A()
        assert a.a == 1
        a.__dict__['b'] = 4
        assert a.b == 4
        assert a.c == "C"
        class A:
            a = 1
            def __setattr__(self, attr, value):
                self.__dict__[attr.lower()] = value
        a = A()
        assert a.a == 1
        a.A = 2
        assert a.a == 2
        class A:
            a = 1
            def __delattr__(self, attr):
                del self.__dict__[attr.lower()]
        a = A()
        assert a.a == 1
        a.a = 2
        assert a.a == 2
        del a.A
        assert a.a == 1

    def test_instance_override(self):
        class A:
            def __str__(self):
                return "foo"
        def __str__():
            return "bar"
        a = A()
        assert str(a) == "foo"
        a.__str__ = __str__
        assert str(a) == "bar"

    def test_unary_method(self):
        class A:
            def __pos__(self):
                 return -1
        a = A()
        assert +a == -1

    def test_cmp(self):
        class A:
            def __lt__(self, other):
                 return True
        a = A()
        b = A()
        assert a < b
        assert b < a
        assert a < 1

    def test_coerce(self):
        class B:
            def __coerce__(self, other):
                return other, self
        b = B()
        assert coerce(b, 1) == (1, b)
        class B:
            pass
        raises(TypeError, coerce, B(), [])

    def test_binaryop(self):
        class A:
            def __add__(self, other):
                return 1 + other
        a = A()
        assert a + 1 == 2
        assert a + 1.1 == 2.1

    def test_binaryop_coerces(self):
        class A:
            def __add__(self, other):
                return 1 + other
            def __coerce__(self, other):
                 return self, int(other)

        a = A()
        assert a + 1 == 2
        assert a + 1.1 == 2


    def test_binaryop_calls_coerce_always(self):
        l = []
        class A:
            def __coerce__(self, other):
                 l.append(other)

        a = A()
        raises(TypeError, "a + 1")
        raises(TypeError, "a + 1.1")
        assert l == [1, 1.1]

    def test_iadd(self):
        class A:
            def __init__(self):
                self.l = []
            def __iadd__(self, other):
                 self.l.append(other)
                 return self
        a1 = a = A()
        a += 1
        assert a is a1
        a += 2
        assert a is a1
        assert a.l == [1, 2]

    def test_cmp(self):
        class A:
            def __coerce__(self, other):
                return (1, 2)
        assert cmp(A(), 1) == -1
        class A:
            def __cmp__(self, other):
                return 1
        class B:
            pass

        a = A()
        b = B()
        assert cmp(a, b) == 1
        assert cmp(b, a) == -1

        class A:
            def __cmp__(self, other):
                return 1L
        a = A()
        assert cmp(a, b) == 1

        class A:
            def __cmp__(self, other):
                return "hello?"
        a = A()
        raises(TypeError, cmp, a, b)

    def test_hash(self):
        class A:
            pass
        hash(A()) # does not crash
        class A:
            def __hash__(self):
                return "hello?"
        a = A()
        raises(TypeError, hash, a)
        class A:
            def __hash__(self):
                return 1
        a = A()
        assert hash(a) == 1
        class A:
            def __cmp__(self, other):
                return 1
        a = A()
        raises(TypeError, hash, a)
        class A:
            def __eq__(self, other):
                return 1
        a = A()
        raises(TypeError, hash, a)

    def test_index(self):
        class A:
            def __index__(self):
                return 1
        l = [1, 2, 3]
        assert l[A()] == 2
        class A:
            pass
        raises(TypeError, "l[A()]")

    def test_contains(self):
        class A:
            def __contains__(self, other):
                return True
        a = A()
        assert 1 in a
        assert None in a
        class A:
            pass
        a = A()
        raises(TypeError, "1 in a")
        class A:
            def __init__(self):
                self.list = [1, 2, 3, 4, 5]
            def __iter__(self):
                return iter(self.list)
        a = A()
        for i in range(1, 6):
            assert i in a
        class A:
            def __init__(self):
                self.list = [1, 2, 3, 4, 5]
            def __len__(self):
                return len(self.list)
            def __getitem__(self, i):
                return self.list[i]
        a = A()
        for i in range(1, 6):
            assert i in a

    def test_pow(self):
        class A:
            def __pow__(self, other, mod=None):
                if mod is None:
                    return 2 ** other
                return mod ** other
        a = A()
        assert a ** 4 == 16
        assert pow(a, 4) == 16
        assert pow(a, 4, 5) == 625
        raises(TypeError, "4 ** a")
        class A:
            def __rpow__(self, other, mod=None):
                if mod is None:
                    return 2 ** other
                return mod ** other
        a = A()
        assert 4 ** a == 16
        assert pow(4, a) == 16
        raises(TypeError, "a ** 4")
        assert pow(4, a, 5) == 625

    def test_getsetdelslice(self):

        class A:
            def __getslice__(self, i, j):
                return i + j
            def __setslice__(self, i, j, seq):
                self.last = (i, j, seq)
            def __delslice__(self, i, j):
                self.last = (i, j, None)
        a = A()
        assert a[1:3] == 4
        a[1:3] = [1, 2, 3]
        assert a.last == (1, 3, [1, 2, 3])
        del a[1:4]
        assert a.last == (1, 4, None)

    def test_contains_bug(self):
        class A:
            def __iter__(self):
                return self
        raises(TypeError, "1 in A()")

    def test_class_instantiation_bug(self):
        raises(TypeError, "class A(1, 2): pass")
        raises(TypeError, "_classobj(1, (), {})")
        raises(TypeError, "_classobj('abc', 1, {})")
        raises(TypeError, "_classobj('abc', (1, ), {})")
        raises(TypeError, "_classobj('abc', (), 3)")

    def test_instance_new(self):
        class A:
            b = 1
        a = A()
        a = type(a).__new__(type(a), A)
        assert a.b == 1
        a = type(a).__new__(type(a), A, None)
        assert a.b == 1
        a = type(a).__new__(type(a), A, {'c': 2})
        assert a.b == 1
        assert a.c == 2
        raises(TypeError, type(a).__new__, type(a), A, 1)

    def test_del(self):
        import gc
        l = []
        class A:
            def __del__(self):
                l.append(1)
        a = A()
        a = None
        gc.collect()
        gc.collect()
        gc.collect()
        assert l == [1]
        class B(A):
            pass
        b = B()
        b = None
        gc.collect()
        gc.collect()
        gc.collect()
        assert l == [1, 1]

    def test_catch_attributeerror_of_descriptor(self):
        def booh(self):
            raise AttributeError, "booh"

        class E:
            __eq__ = property(booh)

        # does not crash
        E() == E()

    def test_multiple_inheritance_more(self):
        l = []
        class A:    # classic class
            def save(self):
                l.append("A")
        class B(A):
            pass
        class C(A):
            def save(self):
                l.append("C")
        class D(B, C):
            pass

        D().save()
        assert l == ['A']

    def test_weakref(self):
        import weakref, gc
        class A:
            pass
        a = A()
        ref = weakref.ref(a)
        assert ref() is a
        a = None
        gc.collect()
        gc.collect()
        gc.collect()
        assert ref() is None

    def test_next(self):
        class X:
            def __iter__(self):
                return Y()
         
        class Y:
            def next(self):
                return 3
         
        for i in X():
            print i,
            break
