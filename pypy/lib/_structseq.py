"""
Implementation helper: a struct that looks like a tuple.  See timemodule
and posixmodule for example uses.
"""

class structseqfield(object):
    """Definition of field of a structseq.  The 'index' is for positional
    tuple-like indexing.  Fields whose index is after a gap in the numbers
    cannot be accessed like this, but only by name.
    """
    def __init__(self, index, doc=None, default=lambda self: None):
        self.__name__ = '?'
        self.index    = index    # patched to None if not positional
        self._index   = index
        self.__doc__  = doc
        self._default = default

    def __repr__(self):
        return '<field %s (%s)>' % (self.__name__,
                                    self.__doc__ or 'undocumented')

    def __get__(self, obj, typ=None):
        if obj is None:
            return self
        if self.index is None:
            return obj.__dict__[self.__name__]
        else:
            return obj[self.index]

    def __set__(self, obj, value):
        raise TypeError("readonly attribute")


class structseqtype(type):

    def __new__(metacls, classname, bases, dict):
        assert not bases
        fields_by_index = {}
        for name, field in dict.items():
            if isinstance(field, structseqfield):
                assert field._index not in fields_by_index
                fields_by_index[field._index] = field
                field.__name__ = name
        dict['n_fields'] = len(fields_by_index)

        extra_fields = fields_by_index.items()
        extra_fields.sort()
        n_sequence_fields = 0
        while extra_fields and extra_fields[0][0] == n_sequence_fields:
            extra_fields.pop(0)
            n_sequence_fields += 1
        dict['n_sequence_fields'] = n_sequence_fields

        extra_fields = [field for index, field in extra_fields]
        for field in extra_fields:
            field.index = None     # no longer relevant

        assert '__new__' not in dict
        dict['_extra_fields'] = tuple(extra_fields)
        dict['__new__'] = structseq_new
        dict['__reduce__'] = structseq_reduce
        return type.__new__(metacls, classname, (tuple,), dict)


builtin_dict = dict

def structseq_new(cls, sequence, dict={}):
    sequence = tuple(sequence)
    dict = builtin_dict(dict)
    N = cls.n_sequence_fields
    if len(sequence) < N:
        if N < cls.n_fields:
            msg = "at least"
        else:
            msg = "exactly"
        raise TypeError("expected a sequence with %s %d items" % (
            msg, N))
    if len(sequence) > N:
        if len(sequence) > cls.n_fields:
            if N < cls.n_fields:
                msg = "at most"
            else:
                msg = "exactly"
            raise TypeError("expected a sequence with %s %d items" % (
                msg, cls.n_fields))
        for field, value in zip(cls._extra_fields, sequence[N:]):
            name = field.__name__
            if name in dict:
                raise TypeError("duplicate value for %r" % (name,))
            dict[name] = value
        sequence = sequence[:N]
    result = tuple.__new__(cls, sequence)
    result.__dict__ = dict
    for field in cls._extra_fields:
        name = field.__name__
        if name not in dict:
            dict[name] = field._default(result)
    return result

def structseq_reduce(self):
    return type(self), (tuple(self), self.__dict__)
