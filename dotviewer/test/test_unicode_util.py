#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
import py
import codecs
from dotviewer.strunicode import RAW_ENCODING, forcestr, forceunicode

SOURCE1 = u"""digraph G{
λ -> b
b -> μ
}
"""

FILENAME = 'test.dot'

class TestUnicodeUtil(object):

    def test_idempotent(self):
        x = u"a"
        assert forceunicode(forcestr(x)) == x
        
        x = u"λ"
        assert forceunicode(forcestr(x)) == x

        assert forceunicode(forcestr(SOURCE1)) == SOURCE1

        x = "a"
        assert forcestr(forceunicode(x)) == x

        # utf-8 encoded.
        # fragile, does not consider RAW_ENCODING
        # x = "\xef\xbb\xbf\xce\xbb"
        # assert forcestr(forceunicode(x)) == x

    def test_does_not_double_encode(self):
        x = u"λ"
        x_e = forcestr(x)
        assert forcestr(x_e) == x_e

        x_u = forceunicode(x_e)
        assert forceunicode(x_u) == x_u

    def test_file(self):       
        udir = py.path.local.make_numbered_dir(prefix='usession-dot-', keep=3)
        full_filename = str(udir.join(FILENAME))
        f = codecs.open(full_filename, 'wb', RAW_ENCODING)
        f.write(SOURCE1)
        f.close()

        with open(full_filename) as f1:
            assert forceunicode(f1.read()) == SOURCE1

        f3 = codecs.open(full_filename, 'r', RAW_ENCODING)
        c = f3.read()
        f3.close()
        result = (c == SOURCE1)
        assert result
