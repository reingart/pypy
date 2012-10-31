from pypy.rlib.rstring import StringBuilder
from pypy.interpreter.baseobjspace import Wrappable
from pypy.interpreter.error import OperationError
from pypy.interpreter.typedef import TypeDef, interp2app
from pypy.interpreter.typedef import interp_attrproperty_w
from pypy.module._csv.interp_csv import _build_dialect
from pypy.module._csv.interp_csv import (QUOTE_MINIMAL, QUOTE_ALL,
                                         QUOTE_NONNUMERIC, QUOTE_NONE)


class W_Writer(Wrappable):

    def __init__(self, space, dialect, w_fileobj):
        self.space = space
        self.dialect = dialect
        self.w_filewrite = space.getattr(w_fileobj, space.wrap('write'))
        # precompute this
        special = dialect.delimiter + dialect.lineterminator
        if dialect.escapechar != '\0': special += dialect.escapechar
        if dialect.quotechar  != '\0': special += dialect.quotechar
        self.special_characters = special

    def error(self, msg):
        space = self.space
        w_module = space.getbuiltinmodule('_csv')
        w_error = space.getattr(w_module, space.wrap('Error'))
        raise OperationError(w_error, space.wrap(msg))
    error._dont_inline_ = True

    def writerow(self, w_fields):
        """Construct and write a CSV record from a sequence of fields.
        Non-string elements will be converted to string."""
        space = self.space
        fields_w = space.listview(w_fields)
        dialect = self.dialect
        rec = StringBuilder(80)
        #
        for field_index in range(len(fields_w)):
            w_field = fields_w[field_index]
            if space.is_w(w_field, space.w_None):
                field = ""
            elif space.isinstance_w(w_field, space.w_float):
                field = space.str_w(space.repr(w_field))
            else:
                field = space.str_w(space.str(w_field))
            #
            if dialect.quoting == QUOTE_NONNUMERIC:
                try:
                    space.float_w(w_field)    # is it an int/long/float?
                    quoted = False
                except OperationError, e:
                    if e.async(space):
                        raise
                    quoted = True
            elif dialect.quoting == QUOTE_ALL:
                quoted = True
            elif dialect.quoting == QUOTE_MINIMAL:
                # Find out if we really quoting
                special_characters = self.special_characters
                for c in field:
                    if c in special_characters:
                        if c != dialect.quotechar or dialect.doublequote:
                            quoted = True
                            break
                else:
                    quoted = False
            else:
                quoted = False

            # If field is empty check if it needs to be quoted
            if len(field) == 0 and len(fields_w) == 1:
                if dialect.quoting == QUOTE_NONE:
                    raise self.error("single empty field record "
                                     "must be quoted")
                quoted = True

            # If this is not the first field we need a field separator
            if field_index > 0:
                rec.append(dialect.delimiter)

            # Handle preceding quote
            if quoted:
                rec.append(dialect.quotechar)

            # Copy field data
            special_characters = self.special_characters
            for c in field:
                if c in special_characters:
                    if dialect.quoting == QUOTE_NONE:
                        want_escape = True
                    else:
                        want_escape = False
                        if c == dialect.quotechar:
                            if dialect.doublequote:
                                rec.append(dialect.quotechar)
                            else:
                                want_escape = True
                    if want_escape:
                        if dialect.escapechar == '\0':
                            raise self.error("need to escape, "
                                             "but no escapechar set")
                        rec.append(dialect.escapechar)
                    else:
                        assert quoted
                # Copy field character into record buffer
                rec.append(c)

            # Handle final quote
            if quoted:
                rec.append(dialect.quotechar)

        # Add line terminator
        rec.append(dialect.lineterminator)

        line = rec.build()
        return space.call_function(self.w_filewrite, space.wrap(line))

    def writerows(self, w_seqseq):
        """Construct and write a series of sequences to a csv file.
        Non-string elements will be converted to string."""
        space = self.space
        w_iter = space.iter(w_seqseq)
        while True:
            try:
                w_seq = space.next(w_iter)
            except OperationError, e:
                if e.match(space, space.w_StopIteration):
                    break
                raise
            self.writerow(w_seq)


def csv_writer(space, w_fileobj, w_dialect=None,
                  w_delimiter        = None,
                  w_doublequote      = None,
                  w_escapechar       = None,
                  w_lineterminator   = None,
                  w_quotechar        = None,
                  w_quoting          = None,
                  w_skipinitialspace = None,
                  w_strict           = None,
                  ):
    """
    csv_writer = csv.writer(fileobj [, dialect='excel']
                            [optional keyword args])
    for row in sequence:
        csv_writer.writerow(row)

    [or]

    csv_writer = csv.writer(fileobj [, dialect='excel']
                            [optional keyword args])
    csv_writer.writerows(rows)

    The \"fileobj\" argument can be any object that supports the file API."""
    dialect = _build_dialect(space, w_dialect, w_delimiter, w_doublequote,
                             w_escapechar, w_lineterminator, w_quotechar,
                             w_quoting, w_skipinitialspace, w_strict)
    return W_Writer(space, dialect, w_fileobj)

W_Writer.typedef = TypeDef(
        'writer',
        __module__ = '_csv',
        dialect = interp_attrproperty_w('dialect', W_Writer),
        writerow = interp2app(W_Writer.writerow),
        writerows = interp2app(W_Writer.writerows),
        __doc__ = """CSV writer

Writer objects are responsible for generating tabular data
in CSV format from sequence input.""")
W_Writer.typedef.acceptable_as_base_class = False