import os
import autopath
# from pypy.appspace import _file
from pypy.tool.udir import udir 
import py 
import unittest

class TestFile: 
    def setup_method(self, method):
        filename = os.path.join(autopath.this_dir, 'test_file.py')
        self.fd = file(filename, 'r')

    def teardown_method(self, method):
        self.fd.close()
        
    def test_case_1(self):
        assert self.fd.tell() == 0

    def test_case_readonly(self):
        fn = str(udir.join('temptestfile'))
        f=file(fn, 'w')
        assert f.name == fn
        assert f.mode == 'w'
        assert f.closed == False
        assert f.encoding == None # Fix when we find out what this is
        py.test.raises(TypeError, setattr, f, 'name', 42)


    def test_from_cpython(self):

        from test.test_support import verify, TESTFN, TestFailed
        from UserList import UserList

        # verify expected attributes exist
        f = file(TESTFN, 'w')
        softspace = f.softspace
        f.name     # merely shouldn't blow up
        f.mode     # ditto
        f.closed   # ditto

        # verify softspace is writable
        f.softspace = softspace    # merely shouldn't blow up

        # verify the others aren't
        for attr in 'name', 'mode', 'closed':
            try:
                setattr(f, attr, 'oops')
            except TypeError:
                pass
            else:
                raise TestFailed('expected TypeError setting file attr %r' % attr)
        f.close()

        # verify writelines with instance sequence
        l = UserList(['1', '2'])
        f = open(TESTFN, 'wb')
        f.writelines(l)
        f.close()
        f = open(TESTFN, 'rb')
        buf = f.read()
        f.close()
        verify(buf == '12')

        # verify writelines with integers
        f = open(TESTFN, 'wb')
        try:
            f.writelines([1, 2, 3])
        except TypeError:
            pass
        else:
            print "writelines accepted sequence of integers"
        f.close()

        # verify writelines with integers in UserList
        f = open(TESTFN, 'wb')
        l = UserList([1,2,3])
        try:
            f.writelines(l)
        except TypeError:
            pass
        else:
            print "writelines accepted sequence of integers"
        f.close()

        # verify writelines with non-string object
        class NonString: pass

        f = open(TESTFN, 'wb')
        try:
            f.writelines([NonString(), NonString()])
        except TypeError:
            pass
        else:
            print "writelines accepted sequence of non-string objects"
        f.close()

        # verify that we get a sensible error message for bad mode argument
        bad_mode = "qwerty"
        try:
            open(TESTFN, bad_mode)
        except IOError, msg:
            pass # We have problems with Exceptions
            if msg[0] != 0:
                s = str(msg)
                if s.find(TESTFN) != -1 or s.find(bad_mode) == -1:
                    print "bad error message for invalid mode: %s" % s
            # if msg[0] == 0, we're probably on Windows where there may be
            # no obvious way to discover why open() failed.
        else:
            print "no error for invalid mode: %s" % bad_mode

        f = open(TESTFN)
        if f.name != TESTFN:
            raise TestFailed, 'file.name should be "%s"' % TESTFN

        if f.isatty():
            raise TestFailed, 'file.isatty() should be false'

        if f.closed:
            raise TestFailed, 'file.closed should be false'


        f.close()
        if not f.closed:
            raise TestFailed, 'file.closed should be true'

        # make sure that explicitly setting the buffer size doesn't cause
        # misbehaviour especially with repeated close() calls
        for s in (-1, 0, 1, 512):
            try:
                f = open(TESTFN, 'w', s)
                f.write(str(s))
                f.close()
                f.close()
                f = open(TESTFN, 'r', s)
                d = int(f.read())
                f.close()
                f.close()
            except IOError, msg:
                raise TestFailed, 'error setting buffer size %d: %s' % (s, str(msg))
            if d != s:
                raise TestFailed, 'readback failure using buffer size %d'

        methods = ['fileno', 'flush', 'isatty', 'next', 'read', 'readline',
                   'readlines', 'seek', 'tell', 'truncate', 'write',
                   'xreadlines', '__iter__']

        for methodname in methods:
            method = getattr(f, methodname)
            try:
                method()
            except ValueError:
                pass
            else:
                raise TestFailed, 'file.%s() on a closed file should raise a ValueError' % methodname

        try:
            f.writelines([])
        except ValueError:
            pass
        else:
            raise TestFailed, 'file.writelines([]) on a closed file should raise a ValueError'

        os.unlink(TESTFN)

        def bug801631():
            # SF bug <http://www.python.org/sf/801631>
            # "file.truncate fault on windows"
            f = file(TESTFN, 'wb')
            f.write('12345678901')   # 11 bytes
            f.close()

            f = file(TESTFN,'rb+')
            data = f.read(5)
            if data != '12345':
                raise TestFailed("Read on file opened for update failed %r" % data)
            if f.tell() != 5:
                raise TestFailed("File pos after read wrong %d" % f.tell())

            f.truncate()
            if f.tell() != 5:
                raise TestFailed("File pos after ftruncate wrong %d" % f.tell())

            f.close()
            size = os.path.getsize(TESTFN)
            if size != 5:
                raise TestFailed("File size after ftruncate wrong %d" % size)

        try:
            bug801631()
        finally:
            os.unlink(TESTFN)
        
