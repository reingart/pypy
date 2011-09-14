from pypy.conftest import gettestobjspace


class AppTestCopy:
    def setup_class(cls):
        cls.space = gettestobjspace(usemodules=('_continuation',),
                                    CALL_METHOD=True)

    def test_basic_setup(self):
        from _continuation import continulet
        lst = [4]
        co = continulet(lst.append)
        assert lst == [4]
        res = co.switch()
        assert res is None
        assert lst == [4, co]

    def test_copy_continulet_not_started(self):
        from _continuation import continulet, error
        import copy
        lst = []
        co = continulet(lst.append)
        co2, lst2 = copy.deepcopy((co, lst))
        #
        assert lst == []
        co.switch()
        assert lst == [co]
        #
        assert lst2 == []
        co2.switch()
        assert lst2 == [co2]

    def test_copy_continulet_real(self):
        import new, sys
        mod = new.module('test_copy_continulet_real')
        sys.modules['test_copy_continulet_real'] = mod
        exec '''if 1:
            from _continuation import continulet
            import copy
            def f(co, x):
                co.switch(x + 1)
                co.switch(x + 2)
                return x + 3
            co = continulet(f, 40)
            res = co.switch()
            assert res == 41
            co2 = copy.deepcopy(co)
            #
            res = co2.switch()
            assert res == 42
            assert co2.is_pending()
            res = co2.switch()
            assert res == 43
            assert not co2.is_pending()
            #
            res = co.switch()
            assert res == 42
            assert co.is_pending()
            res = co.switch()
            assert res == 43
            assert not co.is_pending()
        ''' in mod.__dict__


class AppTestPickle:
    version = 0

    def setup_class(cls):
        cls.space = gettestobjspace(usemodules=('_continuation',),
                                    CALL_METHOD=True)
        cls.space.appexec([], """():
            global continulet, A, __name__

            import sys
            __name__ = 'test_pickle_continulet'
            thismodule = type(sys)(__name__)
            sys.modules[__name__] = thismodule

            from _continuation import continulet
            class A(continulet):
                pass

            thismodule.__dict__.update(globals())
        """)
        cls.w_version = cls.space.wrap(cls.version)

    def test_pickle_continulet_empty(self):
        skip("pickle a not-initialized continulet")
        from _continuation import continulet
        lst = [4]
        co = continulet.__new__(continulet)
        import pickle
        pckl = pickle.dumps(co, self.version)
        print repr(pckl)
        co2 = pickle.loads(pckl)
        assert co2 is not co
        assert not co.is_pending()
        assert not co2.is_pending()
        # the empty unpickled coroutine can still be used:
        result = [5]
        co2.__init__(result.append)
        res = co2.switch()
        assert res is None
        assert result == [5, co2]

    def test_pickle_continulet_empty_subclass(self):
        skip("pickle a not-initialized continulet")
        from test_pickle_continulet import continulet, A
        lst = [4]
        co = continulet.__new__(A)
        co.foo = 'bar'
        co.bar = 'baz'
        import pickle
        pckl = pickle.dumps(co, self.version)
        print repr(pckl)
        co2 = pickle.loads(pckl)
        assert co2 is not co
        assert not co.is_pending()
        assert not co2.is_pending()
        assert type(co) is type(co2) is A
        assert co.foo == co2.foo == 'bar'
        assert co.bar == co2.bar == 'baz'
        # the empty unpickled coroutine can still be used:
        result = [5]
        co2.__init__(result.append)
        res = co2.switch()
        assert res is None
        assert result == [5, co2]

    def test_pickle_continulet_not_started(self):
        from _continuation import continulet, error
        import pickle
        lst = []
        co = continulet(lst.append)
        pckl = pickle.dumps((co, lst))
        print pckl
        co2, lst2 = pickle.loads(pckl)
        assert co is not co2
        assert lst2 == []
        xxx

    def test_pickle_continulet_real(self):
        import new, sys
        mod = new.module('test_pickle_continulet_real')
        sys.modules['test_pickle_continulet_real'] = mod
        mod.version = self.version
        exec '''if 1:
            from _continuation import continulet
            import pickle
            def f(co, x):
                co.switch(x + 1)
                co.switch(x + 2)
                return x + 3
            co = continulet(f, 40)
            res = co.switch()
            assert res == 41
            pckl = pickle.dumps(co, version)
            print repr(pckl)
            co2 = pickle.loads(pckl)
            #
            res = co2.switch()
            assert res == 42
            assert co2.is_pending()
            res = co2.switch()
            assert res == 43
            assert not co2.is_pending()
            #
            res = co.switch()
            assert res == 42
            assert co.is_pending()
            res = co.switch()
            assert res == 43
            assert not co.is_pending()
        ''' in mod.__dict__


class AppTestPickle_v1(AppTestPickle):
    version = 1

class AppTestPickle_v2(AppTestPickle):
    version = 2
