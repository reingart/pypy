import sys
import subprocess
import py
from lib_pypy import disassembler
from pypy.tool.udir import udir
from pypy.tool import logparser
from pypy.module.pypyjit.test_pypy_c.model import Log, find_ids_range, find_ids, \
    LoopWithIds, OpMatcher

class BaseTestPyPyC(object):
    def setup_class(cls):
        if '__pypy__' not in sys.builtin_module_names:
            py.test.skip("must run this test with pypy")
        if not sys.pypy_translation_info['translation.jit']:
            py.test.skip("must give a pypy-c with the jit enabled")
        cls.tmpdir = udir.join('test-pypy-jit')
        cls.tmpdir.ensure(dir=True)

    def setup_method(self, meth):
        self.filepath = self.tmpdir.join(meth.im_func.func_name + '.py')

    def run(self, func, args=[], **jitopts):
        # write the snippet
        arglist = ', '.join(map(repr, args))
        with self.filepath.open("w") as f:
            f.write(str(py.code.Source(func)) + "\n")
            f.write("print %s(%s)\n" % (func.func_name, arglist))
        #
        # run a child pypy-c with logging enabled
        logfile = self.filepath.new(ext='.log')
        #
        cmdline = [sys.executable, '-S']
        for key, value in jitopts.iteritems():
            cmdline += ['--jit', '%s=%s' % (key, value)]
        cmdline.append(str(self.filepath))
        #
        env={'PYPYLOG': 'jit-log-opt,jit-summary:' + str(logfile)}
        pipe = subprocess.Popen(cmdline,
                                env=env,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        pipe.wait()
        stderr = pipe.stderr.read()
        stdout = pipe.stdout.read()
        assert not stderr
        #
        # parse the JIT log
        rawlog = logparser.parse_log_file(str(logfile))
        rawtraces = logparser.extract_category(rawlog, 'jit-log-opt-')
        log = Log(func, rawtraces)
        log.result = eval(stdout)
        return log


class TestLog(object):

    def test_find_ids_range(self):
        def f():
            a = 0 # ID: myline
            return a
        #
        start_lineno = f.func_code.co_firstlineno
        code = disassembler.dis(f)
        ids = find_ids_range(code)
        assert len(ids) == 1
        myline_range = ids['myline']
        assert list(myline_range) == range(start_lineno+1, start_lineno+2)

    def test_find_ids(self):
        def f():
            i = 0
            x = 0
            z = x + 3 # ID: myline
            return z
        #
        code = disassembler.dis(f)
        ids = find_ids(code)
        assert len(ids) == 1
        myline = ids['myline']
        opcodes_names = [opcode.__class__.__name__ for opcode in myline]
        assert opcodes_names == ['LOAD_FAST', 'LOAD_CONST', 'BINARY_ADD', 'STORE_FAST']

class TestOpMatcher(object):

    def match(self, src1, src2):
        from pypy.tool.jitlogparser.parser import parse
        loop = parse(src1)
        matcher = OpMatcher(loop.operations)
        return matcher.match(src2)

    def test_match_var(self):
        match_var = OpMatcher([]).match_var
        assert match_var('v0', 'V0')
        assert not match_var('v0', 'V1')
        assert match_var('v0', 'V0')
        #
        # for ConstPtr, we allow the same alpha-renaming as for variables
        assert match_var('ConstPtr(ptr0)', 'PTR0')
        assert not match_var('ConstPtr(ptr0)', 'PTR1')
        assert match_var('ConstPtr(ptr0)', 'PTR0')
        #
        # for ConstClass, we want the exact matching
        assert match_var('ConstClass(foo)', 'ConstClass(foo)')
        assert not match_var('ConstClass(bar)', 'v1')
        assert not match_var('v2', 'ConstClass(baz)')
        #
        # the var '_' matches everything (but only on the right, of course)
        assert match_var('v0', '_')
        assert match_var('v0', 'V0')
        assert match_var('ConstPtr(ptr0)', '_')
        py.test.raises(AssertionError, "match_var('_', 'v0')")

    def test_parse_op(self):
        res = OpMatcher.parse_op("  a =   int_add(  b,  3 ) # foo")
        assert res == ("int_add", "a", ["b", "3"])
        res = OpMatcher.parse_op("guard_true(a)")
        assert res == ("guard_true", None, ["a"])

    def test_exact_match(self):
        loop = """
            [i0]
            i2 = int_add(i0, 1)
            jump(i2)
        """
        expected = """
            i5 = int_add(i2, 1)
            jump(i5)
        """
        assert self.match(loop, expected)
        #
        expected = """
            i5 = int_sub(i2, 1)
            jump(i5)
        """
        assert not self.match(loop, expected)
        #
        expected = """
            i5 = int_add(i2, 1)
            jump(i5)
            extra_stuff(i5)
        """
        assert not self.match(loop, expected)
        #
        expected = """
            i5 = int_add(i2, 1)
            # missing op at the end
        """
        assert not self.match(loop, expected)


    def test_partial_match(self):
        py.test.skip('in-progress')
        loop = """
            [i0]
            i1 = int_add(i0, 1)
            i2 = int_sub(i1, 10)
            i3 = int_floordiv(i2, 100)
            i4 = int_mul(i1, 1000)
            jump(i3)
        """
        expected = """
            i1 = int_add(0, 1)
            ...
            i4 = int_mul(i1, 1000)
        """
        assert self.match(loop, expected)


class TestRunPyPyC(BaseTestPyPyC):

    def test_run_function(self):
        def f(a, b):
            return a+b
        log = self.run(f, [30, 12])
        assert log.result == 42

    def test_parse_jitlog(self):
        def f():
            i = 0
            while i < 1003:
                i += 1
            return i
        #
        log = self.run(f)
        assert log.result == 1003
        loops = log.loops_by_filename(self.filepath)
        assert len(loops) == 1
        assert loops[0].filename == self.filepath
        assert not loops[0].is_entry_bridge
        #
        loops = log.loops_by_filename(self.filepath, is_entry_bridge=True)
        assert len(loops) == 1
        assert loops[0].is_entry_bridge
        #
        loops = log.loops_by_filename(self.filepath, is_entry_bridge='*')
        assert len(loops) == 2

    def test_loops_by_id(self):
        def f():
            i = 0
            while i < 1003:
                i += 1 # ID: increment
            return i
        #
        log = self.run(f)
        loop, = log.loops_by_id('increment')
        assert loop.filename == self.filepath
        assert loop.code.co.co_name == 'f'
        #
        ops = loop.allops()
        assert log.opnames(ops) == [
            # this is the actual loop
            'int_lt', 'guard_true', 'int_add',
            # this is the signal checking stuff
            'getfield_raw', 'int_sub', 'setfield_raw', 'int_lt', 'guard_false',
            'jump'
            ]

    def test_ops_by_id(self):
        def f():
            i = 0
            while i < 1003:
                i += 1 # ID: increment
                a = 0  # to make sure that JUMP_ABSOLUTE is not part of the ID
            return i
        #
        log = self.run(f)
        loop, = log.loops_by_id('increment')
        #
        ops = loop.ops_by_id('increment')
        assert log.opnames(ops) == ['int_add']

    def test_ops_by_id_and_opcode(self):
        def f():
            i = 0
            j = 0
            while i < 1003:
                i += 1; j -= 1 # ID: foo
                a = 0  # to make sure that JUMP_ABSOLUTE is not part of the ID
            return i
        #
        log = self.run(f)
        loop, = log.loops_by_id('foo')
        #
        ops = loop.ops_by_id('foo', opcode='INPLACE_ADD')
        assert log.opnames(ops) == ['int_add']
        #
        ops = loop.ops_by_id('foo', opcode='INPLACE_SUBTRACT')
        assert log.opnames(ops) == ['int_sub_ovf', 'guard_no_overflow']
        

    def test_inlined_function(self):
        def f():
            def g(x):
                return x+1 # ID: add
            i = 0
            while i < 1003:
                i = g(i) # ID: call
                a = 0    # to make sure that JUMP_ABSOLUTE is not part of the ID
            return i
        #
        log = self.run(f)
        loop, = log.loops_by_filename(self.filepath)
        call_ops = log.opnames(loop.ops_by_id('call'))
        assert call_ops == ['force_token'] # it does not follow inlining
        #
        add_ops = log.opnames(loop.ops_by_id('add'))
        assert add_ops == ['int_add']
        #
        ops = log.opnames(loop.allops())
        assert ops == [
            # this is the actual loop
            'int_lt', 'guard_true', 'force_token', 'int_add',
            # this is the signal checking stuff
            'getfield_raw', 'int_sub', 'setfield_raw', 'int_lt', 'guard_false',
            'jump'
            ]

    def test_match(self):
        def f():
            i = 0
            while i < 1003:
                i += 1 # ID: increment
            return i
        #
        log = self.run(f)
        loop, = log.loops_by_id('increment')
        assert loop.match("""
            i6 = int_lt(i4, 1003)
            guard_true(i6)
            i8 = int_add(i4, 1)
            # signal checking stuff
            i10 = getfield_raw(37212896)
            i12 = int_sub(i10, 1)
            setfield_raw(37212896, i12)
            i14 = int_lt(i12, 0)
            guard_false(i14)
            jump(p0, p1, p2, p3, i8)
        """)
        #
        assert loop.match("""
            i6 = int_lt(i4, 1003)
            guard_true(i6)
            i8 = int_add(i4, 1)
            --TICK--
            jump(p0, p1, p2, p3, i8)
        """)
        #
        assert not loop.match("""
            i6 = int_lt(i4, 1003)
            guard_true(i6)
            i8 = int_add(i5, 1) # variable mismatch
            --TICK--
            jump(p0, p1, p2, p3, i8)
        """)

    def test_match_by_id(self):
        def f():
            i = 0
            j = 2000
            while i < 1003:
                i += 1 # ID: increment
                j -= 1 # ID: product
                a = 0  # to make sure that JUMP_ABSOLUTE is not part of the ID
            return i
        #
        log = self.run(f)
        loop, = log.loops_by_id('increment')
        assert loop.match_by_id('increment', """
            i1 = int_add(i0, 1)
        """)
        assert loop.match_by_id('product', """
            i4 = int_sub_ovf(i3, 1)
            guard_no_overflow()
        """)

    def test_match_constants(self):
        def f():
            i = 0L # force it to long, so that we get calls to rbigint
            while i < 1003:
                i += 1L # ID: increment
                a = 0
            return i
        log = self.run(f)
        loop, = log.loops_by_id('increment')
        assert loop.match_by_id('increment', """
            p12 = call(ConstClass(rbigint.add), p4, ConstPtr(ptr11))
            guard_no_exception()
        """)
        #
        assert not loop.match_by_id('increment', """
            p12 = call(ConstClass(rbigint.SUB), p4, ConstPtr(ptr11))
            guard_no_exception()
        """)
        
