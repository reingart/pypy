from __future__ import generators
from py import test, magic

class TestCompatTestCaseSetupSemantics(test.compat.TestCase): 
    globlist = []

    def setUp(self):
        self.__dict__.setdefault('l', []).append(42)
        self.globlist.append(self)

    def tearDown(self):
        self.l.pop()

    def test_issetup(self):
        l = self.l
        assert len(l) == 1
        assert l[-1] == 42
        self.checkmultipleinstances()

    def test_issetup2(self):
        l = self.l
        assert len(l) == 1
        assert l[-1] == 42
        self.checkmultipleinstances()

    def checkmultipleinstances(self):
        for x,y in zip(self.globlist, self.globlist[1:]):
            assert x is not y

class TestCompatAssertions(test.compat.TestCase):
    nameparamdef = {
        'failUnlessEqual,assertEqual,assertEquals': ('1, 1', '1, 0'),
        'assertNotEquals,failIfEqual': ('0, 1', '0,0'),
        'failUnless,assert_': ('1', 'None'),
        'failIf': ('0', '1'),
        }

    sourcelist = []
    for names, (paramok, paramfail) in nameparamdef.items():
        for name in names.split(','):
            source = """
            def test_%(name)s(self):
                self.%(name)s(%(paramok)s)
                #self.%(name)s(%(paramfail)s)

            def test_%(name)s_failing(self):
                self.assertRaises(test.run.Failed, 
                            self.%(name)s, %(paramfail)s)
            """ % locals()
            co = magic.dyncode.compile2(source)
            exec co 

test.main()
