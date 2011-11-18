from pypy.interpreter.baseobjspace import Wrappable
from pypy.interpreter.error import OperationError, operationerrfmt
from pypy.interpreter.gateway import interp2app, unwrap_spec, NoneNotWrapped
from pypy.interpreter.typedef import TypeDef, GetSetProperty
from pypy.module.micronumpy import interp_ufuncs, interp_dtype, signature
from pypy.rlib import jit
from pypy.rpython.lltypesystem import lltype
from pypy.tool.sourcetools import func_with_new_name
from pypy.rlib.rstring import StringBuilder

numpy_driver = jit.JitDriver(greens = ['signature'],
                             reds = ['result_size', 'i', 'ri', 'self',
                                     'result'])
all_driver = jit.JitDriver(greens=['signature'], reds=['i', 'self', 'dtype'])
any_driver = jit.JitDriver(greens=['signature'], reds=['i', 'self', 'dtype'])
slice_driver = jit.JitDriver(greens=['signature'], reds=['self', 'source',
                                                         'source_iter',
                                                         'res_iter'])

def _find_shape_and_elems(space, w_iterable):
    shape = [space.len_w(w_iterable)]
    batch = space.listview(w_iterable)
    while True:
        new_batch = []
        if not batch:
            return shape, []
        if not space.issequence_w(batch[0]):
            for elem in batch:
                if space.issequence_w(elem):
                    raise OperationError(space.w_ValueError, space.wrap(
                        "setting an array element with a sequence"))
            return shape, batch
        size = space.len_w(batch[0])
        for w_elem in batch:
            if not space.issequence_w(w_elem) or space.len_w(w_elem) != size:
                raise OperationError(space.w_ValueError, space.wrap(
                    "setting an array element with a sequence"))
            new_batch += space.listview(w_elem)
        shape.append(size)
        batch = new_batch

def descr_new_array(space, w_subtype, w_item_or_iterable, w_dtype=None,
                    w_order=NoneNotWrapped):
    # find scalar
    if not space.issequence_w(w_item_or_iterable):
        w_dtype = interp_ufuncs.find_dtype_for_scalar(space,
                                                      w_item_or_iterable,
                                                      w_dtype)
        dtype = space.interp_w(interp_dtype.W_Dtype,
           space.call_function(space.gettypefor(interp_dtype.W_Dtype), w_dtype))
        return scalar_w(space, dtype, w_item_or_iterable)
    if w_order is None:
        order = 'C'
    else:
        order = space.str_w(w_order)
        if order != 'C':  # or order != 'F':
            raise operationerrfmt(space.w_ValueError, "Unknown order: %s",
                                  order)
    shape, elems_w = _find_shape_and_elems(space, w_item_or_iterable)
    # they come back in C order
    size = len(elems_w)
    if space.is_w(w_dtype, space.w_None):
        w_dtype = None
        for w_elem in elems_w:
            w_dtype = interp_ufuncs.find_dtype_for_scalar(space, w_elem,
                                                          w_dtype)
            if w_dtype is space.fromcache(interp_dtype.W_Float64Dtype):
                break
    if w_dtype is None:
        w_dtype = space.w_None
    dtype = space.interp_w(interp_dtype.W_Dtype,
        space.call_function(space.gettypefor(interp_dtype.W_Dtype), w_dtype)
    )
    arr = NDimArray(size, shape[:], dtype=dtype, order=order)
    arr_iter = arr.start_iter()
    for i in range(len(elems_w)):
        w_elem = elems_w[i]
        dtype.setitem_w(space, arr.storage, arr_iter.offset, w_elem)
        arr_iter = arr_iter.next()
    return arr

class BaseIterator(object):
    def next(self):
        raise NotImplementedError

    def done(self):
        raise NotImplementedError

    def get_offset(self):
        raise NotImplementedError

class ArrayIterator(BaseIterator):
    def __init__(self, size, offset=0):
        self.offset = offset
        self.size   = size

    def next(self):
        return ArrayIterator(self.size, self.offset + 1)

    def done(self):
        return self.offset >= self.size

    def get_offset(self):
        return self.offset

class ViewIterator(BaseIterator):
    def __init__(self, arr, offset=0, indices=None, done=False):
        if indices is None:
            self.indices = [0] * len(arr.shape)
            self.offset  = arr.start
        else:
            self.offset  = offset
            self.indices = indices
        self.arr   = arr
        self._done = done

    @jit.unroll_safe
    def next(self):
        indices = [0] * len(self.arr.shape)
        for i in range(len(self.arr.shape)):
            indices[i] = self.indices[i]
        done = False
        offset = self.offset
        for i in range(len(self.arr.shape) -1, -1, -1):
            if indices[i] < self.arr.shape[i] - 1:
                indices[i] += 1
                offset += self.arr.shards[i]
                break
            else:
                indices[i] = 0
                offset -= self.arr.backshards[i]
        else:
            done = True
        return ViewIterator(self.arr, offset, indices, done)

    def done(self):
        return self._done

    def get_offset(self):
        return self.offset

class Call2Iterator(BaseIterator):
    def __init__(self, left, right):
        self.left = left
        self.right = right

    def next(self):
        return Call2Iterator(self.left.next(), self.right.next())

    def done(self):
        return self.left.done() or self.right.done()

    def get_offset(self):
        if isinstance(self.left, ConstantIterator):
            return self.right.get_offset()
        return self.left.get_offset()

class Call1Iterator(BaseIterator):
    def __init__(self, child):
        self.child = child

    def next(self):
        return Call1Iterator(self.child.next())

    def done(self):
        return self.child.done()

    def get_offset(self):
        return self.child.get_offset()

class ConstantIterator(BaseIterator):
    def next(self):
        return self

    def done(self):
        return False

    def get_offset(self):
        return 0

class BaseArray(Wrappable):
    _attrs_ = ["invalidates", "signature", "shape", "shards", "backshards",
               "start", 'order']

    _immutable_fields_ = ['shape[*]', "shards[*]", "backshards[*]", 'start',
                          "order"]

    shards = None
    start = 0

    def __init__(self, shape, order):
        self.invalidates = []
        self.shape = shape
        self.order = order
        if self.shards is None:
            shards = []
            backshards = []
            s = 1
            shape_rev = shape[:]
            if order == 'C':
                shape_rev.reverse()
            for sh in shape_rev:
                shards.append(s)
                backshards.append(s * (sh - 1))
                s *= sh
            if order == 'C':
                shards.reverse()
                backshards.reverse()
            self.shards = shards[:]
            self.backshards = backshards[:]

    def invalidated(self):
        if self.invalidates:
            self._invalidated()

    def _invalidated(self):
        for arr in self.invalidates:
            arr.force_if_needed()
        del self.invalidates[:]

    def add_invalidates(self, other):
        self.invalidates.append(other)

    def _unaryop_impl(ufunc_name):
        def impl(self, space):
            return getattr(interp_ufuncs.get(space), ufunc_name).call(space, [self])
        return func_with_new_name(impl, "unaryop_%s_impl" % ufunc_name)

    descr_pos = _unaryop_impl("positive")
    descr_neg = _unaryop_impl("negative")
    descr_abs = _unaryop_impl("absolute")

    def _binop_impl(ufunc_name):
        def impl(self, space, w_other):
            return getattr(interp_ufuncs.get(space), ufunc_name).call(space, [self, w_other])
        return func_with_new_name(impl, "binop_%s_impl" % ufunc_name)

    descr_add = _binop_impl("add")
    descr_sub = _binop_impl("subtract")
    descr_mul = _binop_impl("multiply")
    descr_div = _binop_impl("divide")
    descr_pow = _binop_impl("power")
    descr_mod = _binop_impl("mod")

    descr_eq = _binop_impl("equal")
    descr_ne = _binop_impl("not_equal")
    descr_lt = _binop_impl("less")
    descr_le = _binop_impl("less_equal")
    descr_gt = _binop_impl("greater")
    descr_ge = _binop_impl("greater_equal")

    def _binop_right_impl(ufunc_name):
        def impl(self, space, w_other):
            w_other = scalar_w(space,
                interp_ufuncs.find_dtype_for_scalar(space, w_other, self.find_dtype()),
                w_other
            )
            return getattr(interp_ufuncs.get(space), ufunc_name).call(space, [w_other, self])
        return func_with_new_name(impl, "binop_right_%s_impl" % ufunc_name)

    descr_radd = _binop_right_impl("add")
    descr_rsub = _binop_right_impl("subtract")
    descr_rmul = _binop_right_impl("multiply")
    descr_rdiv = _binop_right_impl("divide")
    descr_rpow = _binop_right_impl("power")
    descr_rmod = _binop_right_impl("mod")

    def _reduce_ufunc_impl(ufunc_name):
        def impl(self, space):
            return getattr(interp_ufuncs.get(space), ufunc_name).descr_reduce(space, self)
        return func_with_new_name(impl, "reduce_%s_impl" % ufunc_name)

    descr_sum = _reduce_ufunc_impl("add")
    descr_prod = _reduce_ufunc_impl("multiply")
    descr_max = _reduce_ufunc_impl("maximum")
    descr_min = _reduce_ufunc_impl("minimum")

    def _reduce_argmax_argmin_impl(op_name):
        reduce_driver = jit.JitDriver(greens=['signature'],
                         reds = ['i', 'result', 'self', 'cur_best', 'dtype'])
        def loop(self):
            i = self.start_iter()
            result = i.get_offset()
            cur_best = self.eval(i)
            i.next()
            dtype = self.find_dtype()
            while not i.done():
                reduce_driver.jit_merge_point(signature=self.signature,
                                              self=self, dtype=dtype,
                                              i=i, result=result,
                                              cur_best=cur_best)
                new_best = getattr(dtype, op_name)(cur_best, self.eval(i))
                if dtype.ne(new_best, cur_best):
                    result = i.get_offset()
                    cur_best = new_best
                i = i.next()
            return result
        def impl(self, space):
            size = self.find_size()
            if size == 0:
                raise OperationError(space.w_ValueError,
                    space.wrap("Can't call %s on zero-size arrays" \
                            % op_name))
            return self.compute_index(space, loop(self))
        return func_with_new_name(impl, "reduce_arg%s_impl" % op_name)

    def _all(self):
        dtype = self.find_dtype()
        i = self.start_iter()
        while not i.done():
            all_driver.jit_merge_point(signature=self.signature, self=self, dtype=dtype, i=i)
            if not dtype.bool(self.eval(i)):
                return False
            i = i.next()
        return True
    def descr_all(self, space):
        return space.wrap(self._all())

    def _any(self):
        dtype = self.find_dtype()
        i = self.start_iter()
        while not i.done():
            any_driver.jit_merge_point(signature=self.signature, self=self,
                                       dtype=dtype, i=i)
            if dtype.bool(self.eval(i)):
                return True
            i = i.next()
        return False
    def descr_any(self, space):
        return space.wrap(self._any())

    descr_argmax = _reduce_argmax_argmin_impl("max")
    descr_argmin = _reduce_argmax_argmin_impl("min")

    def descr_dot(self, space, w_other):
        w_other = convert_to_array(space, w_other)
        if isinstance(w_other, Scalar):
            return self.descr_mul(space, w_other)
        else:
            w_res = self.descr_mul(space, w_other)
            assert isinstance(w_res, BaseArray)
            return w_res.descr_sum(space)

    def get_concrete(self):
        raise NotImplementedError

    def descr_get_dtype(self, space):
        return space.wrap(self.find_dtype())

    def descr_get_shape(self, space):
        return space.newtuple([space.wrap(i) for i in self.shape])

    def descr_copy(self, space):
        return space.call_function(space.gettypefor(BaseArray), self, self.find_dtype())

    def descr_len(self, space):
        return self.get_concrete().descr_len(space)

    def descr_repr(self, space):
        res = StringBuilder()
        res.append("array(")
        concrete = self.get_concrete()
        dtype = concrete.find_dtype()
        if not concrete.find_size():
            res.append('[]')
            if len(self.shape) > 1:
                #This is for numpy compliance: an empty slice reports its shape
                res.append(", shape=(")
                self_shape = str(self.shape)
                res.append_slice(str(self_shape), 1, len(self_shape) - 1)
                res.append(')')
        else:
            self.to_str(space, 1, res, indent='       ')
        if (dtype is not space.fromcache(interp_dtype.W_Float64Dtype) and
            dtype is not space.fromcache(interp_dtype.W_Int64Dtype)) or \
            not self.find_size():
            res.append(", dtype=" + dtype.name)
        res.append(")")
        return space.wrap(res.build())

    def to_str(self, space, comma, builder, indent=' ', use_ellipsis=False):
        '''Modifies builder with a representation of the array/slice
        The items will be seperated by a comma if comma is 1
        Multidimensional arrays/slices will span a number of lines,
        each line will begin with indent.
        '''
        if self.size < 1:
            builder.append('[]')
            return
        if self.size > 1000:
            #Once this goes True it does not go back to False for recursive calls
            use_ellipsis = True
        dtype = self.find_dtype()
        ndims = len(self.shape)
        i = 0
        start = True
        builder.append('[')
        if ndims > 1:
            if use_ellipsis:
                for i in range(3):
                    if start:
                        start = False
                    else:
                        builder.append(',' * comma + '\n')
                        if ndims == 3:
                            builder.append('\n' + indent)
                        else:
                            builder.append(indent)
                    #create_slice requires len(chunks)>1 in order to reduce shape
                    view = self.create_slice(space, [(i, 0, 0, 1), (0, self.shape[1], 1, self.shape[1])])
                    view.to_str(space, comma, builder, indent=indent + ' ', use_ellipsis=use_ellipsis)
                builder.append('\n' + indent + '..., ')
                i = self.shape[0] - 3
            while i < self.shape[0]:
                if start:
                    start = False
                else:
                    builder.append(',' * comma + '\n')
                    if ndims == 3:
                        builder.append('\n' + indent)
                    else:
                        builder.append(indent)
                #create_slice requires len(chunks)>1 in order to reduce shape
                view = self.create_slice(space, [(i, 0, 0, 1), (0, self.shape[1], 1, self.shape[1])])
                view.to_str(space, comma, builder, indent=indent + ' ', use_ellipsis=use_ellipsis)
                i += 1
        elif ndims == 1:
            #This should not directly access the start,shards: what happens if order changes?
            spacer = ',' * comma + ' '
            item = self.start
            i = 0
            if use_ellipsis:
                for i in range(3):
                    if start:
                        start = False
                    else:
                        builder.append(spacer)
                    builder.append(dtype.str_format(self.getitem(item)))
                    item += self.shards[0]
                #Add a comma only if comma is False - this prevents adding two commas
                builder.append(spacer + '...' + ',' * (1 - comma))
                item = self.start + self.backshards[0] - 2 * self.shards[0]
                i = self.shape[0] - 3
            while i < self.shape[0]:
                if start:
                    start = False
                else:
                    builder.append(spacer)
                builder.append(dtype.str_format(self.getitem(item)))
                item += self.shards[0]
                i += 1
        else:
            builder.append('[')
        builder.append(']')

    def descr_str(self, space):
        ret = StringBuilder()
        self.to_str(space, 0, ret, ' ')
        return space.wrap(ret.build())

    def _index_of_single_item(self, space, w_idx):
        if space.isinstance_w(w_idx, space.w_int):
            idx = space.int_w(w_idx)
            if not self.shape:
                if idx != 0:
                    raise OperationError(space.w_IndexError,
                                         space.wrap("index out of range"))
                return 0
            if idx < 0:
                idx = self.shape[0] + idx
            if idx < 0 or idx >= self.shape[0]:
                raise OperationError(space.w_IndexError,
                                     space.wrap("index out of range"))
            return self.start + idx * self.shards[0]
        index = [space.int_w(w_item)
                 for w_item in space.fixedview(w_idx)]
        item = self.start
        for i in range(len(index)):
            v = index[i]
            if v < 0:
                v += self.shape[i]
            if v < 0 or v >= self.shape[i]:
                raise OperationError(space.w_IndexError,
                                     space.wrap("index (%d) out of range (0<=index<%d" % (i, self.shape[i])))
            item += v * self.shards[i]
        return item

    def get_root_shape(self):
        return self.shape

    def _single_item_result(self, space, w_idx):
        """ The result of getitem/setitem is a single item if w_idx
        is a list of scalars that match the size of shape
        """
        shape_len = len(self.shape)
        if shape_len == 0:
            if not space.isinstance_w(w_idx, space.w_int):
                raise OperationError(space.w_IndexError, space.wrap(
                    "wrong index"))
            return True
        if shape_len == 1:
            if space.isinstance_w(w_idx, space.w_int):
                return True
            if space.isinstance_w(w_idx, space.w_slice):
                return False
        elif (space.isinstance_w(w_idx, space.w_slice) or
              space.isinstance_w(w_idx, space.w_int)):
            return False
        lgt = space.len_w(w_idx)
        if lgt > shape_len:
            raise OperationError(space.w_IndexError,
                                 space.wrap("invalid index"))
        if lgt < shape_len:
            return False
        for w_item in space.fixedview(w_idx):
            if space.isinstance_w(w_item, space.w_slice):
                return False
        return True

    def _prepare_slice_args(self, space, w_idx):
        if (space.isinstance_w(w_idx, space.w_int) or
            space.isinstance_w(w_idx, space.w_slice)):
            return [space.decode_index4(w_idx, self.shape[0])]
        return [space.decode_index4(w_item, self.shape[i]) for i, w_item in
                enumerate(space.fixedview(w_idx))]

    def descr_getitem(self, space, w_idx):
        if self._single_item_result(space, w_idx):
            concrete = self.get_concrete()
            item = concrete._index_of_single_item(space, w_idx)
            return concrete.getitem(item).wrap(space)
        chunks = self._prepare_slice_args(space, w_idx)
        return space.wrap(self.create_slice(space, chunks))

    def descr_setitem(self, space, w_idx, w_value):
        self.invalidated()
        concrete = self.get_concrete()
        if self._single_item_result(space, w_idx):
            item = concrete._index_of_single_item(space, w_idx)
            concrete.setitem_w(space, item, w_value)
            return
        if isinstance(w_value, BaseArray):
            # for now we just copy if setting part of an array from
            # part of itself. can be improved.
            if (concrete.get_root_storage() ==
                w_value.get_concrete().get_root_storage()):
                w_value = space.call_function(space.gettypefor(BaseArray), w_value)
                assert isinstance(w_value, BaseArray)
        else:
            w_value = convert_to_array(space, w_value)
        chunks = self._prepare_slice_args(space, w_idx)
        view = self.create_slice(space, chunks)
        view.setslice(space, w_value)

    def create_slice(self, space, chunks):
        new_sig = signature.Signature.find_sig([
            NDimSlice.signature, self.signature
        ])
        if len(chunks) == 1:
            start, stop, step, lgt = chunks[0]
            if step == 0:
                shape = self.shape[1:]
                shards = self.shards[1:]
                backshards = self.backshards[1:]
            else:
                shape = [lgt] + self.shape[1:]
                shards = [self.shards[0] * step] + self.shards[1:]
                backshards = [(lgt - 1) * self.shards[0] * step] + self.backshards[1:]
            start *= self.shards[0]
            start += self.start
        else:
            shape = []
            shards = []
            backshards = []
            start = self.start
            i = -1
            for i, (start_, stop, step, lgt) in enumerate(chunks):
                if step != 0:
                    shape.append(lgt)
                    shards.append(self.shards[i] * step)
                    backshards.append(self.shards[i] * (lgt - 1) * step)
                start += self.shards[i] * start_
            # add a reminder
            s = i + 1
            assert s >= 0
            shape += self.shape[s:]
            shards += self.shards[s:]
            backshards += self.backshards[s:]
        return NDimSlice(self, new_sig, start, shards[:], backshards[:],
                         shape[:])

    def descr_mean(self, space):
        return space.wrap(space.float_w(self.descr_sum(space)) / self.find_size())

    def descr_nonzero(self, space):
        try:
            if self.find_size() > 1:
                raise OperationError(space.w_ValueError, space.wrap(
                    "The truth value of an array with more than one element is ambiguous. Use a.any() or a.all()"))
        except ValueError:
            pass
        return space.wrap(space.is_true(self.get_concrete().eval(
            self.start_iter()).wrap(space)))

    def getitem(self, item):
        raise NotImplementedError

    def start_iter(self):
        raise NotImplementedError

    def compute_index(self, space, offset):
        offset -= self.start
        if len(self.shape) == 1:
            return space.wrap(offset // self.shards[0])
        indices_w = []
        for shard in self.shards:
            r = offset // shard
            indices_w.append(space.wrap(r))
            offset -= shard * r
        return space.newtuple(indices_w)

def convert_to_array(space, w_obj):
    if isinstance(w_obj, BaseArray):
        return w_obj
    elif space.issequence_w(w_obj):
        # Convert to array.
        w_obj = space.call_function(space.gettypefor(BaseArray), w_obj)
        assert isinstance(w_obj, BaseArray)
        return w_obj
    else:
        # If it's a scalar
        dtype = interp_ufuncs.find_dtype_for_scalar(space, w_obj)
        return scalar_w(space, dtype, w_obj)

def scalar_w(space, dtype, w_obj):
    assert isinstance(dtype, interp_dtype.W_Dtype)
    return Scalar(dtype, dtype.unwrap(space, w_obj))

class Scalar(BaseArray):
    """
    Intermediate class representing a literal.
    """
    signature = signature.BaseSignature()

    _attrs_ = ["dtype", "value", "shape"]

    def __init__(self, dtype, value):
        BaseArray.__init__(self, [], 'C')
        self.dtype = dtype
        self.value = value

    def find_size(self):
        raise ValueError

    def get_concrete(self):
        return self

    def find_dtype(self):
        return self.dtype

    def getitem(self, item):
        return self.value

    def eval(self, iter):
        return self.value

    def start_iter(self):
        return ConstantIterator()

    def to_str(self, space, comma, builder, indent=' '):
        builder.append(self.dtype.str_format(self.value))

class VirtualArray(BaseArray):
    """
    Class for representing virtual arrays, such as binary ops or ufuncs
    """
    def __init__(self, signature, shape, res_dtype, order):
        BaseArray.__init__(self, shape, order)
        self.forced_result = None
        self.signature = signature
        self.res_dtype = res_dtype

    def _del_sources(self):
        # Function for deleting references to source arrays, to allow garbage-collecting them
        raise NotImplementedError

    def compute(self):
        i = 0
        signature = self.signature
        result_size = self.find_size()
        result = NDimArray(result_size, self.shape, self.find_dtype())
        i = self.start_iter()
        ri = result.start_iter()
        while not ri.done():
            numpy_driver.jit_merge_point(signature=signature,
                                         result_size=result_size, i=i, ri=ri,
                                         self=self, result=result)
            result.dtype.setitem(result.storage, ri.offset, self.eval(i))
            i = i.next()
            ri = ri.next()
        return result

    def force_if_needed(self):
        if self.forced_result is None:
            self.forced_result = self.compute()
            self._del_sources()

    def get_concrete(self):
        self.force_if_needed()
        return self.forced_result

    def eval(self, iter):
        if self.forced_result is not None:
            return self.forced_result.eval(iter)
        return self._eval(iter)

    def getitem(self, item):
        return self.get_concrete().getitem(item)

    def setitem(self, item, value):
        return self.get_concrete().setitem(item, value)

    def find_size(self):
        if self.forced_result is not None:
            # The result has been computed and sources may be unavailable
            return self.forced_result.find_size()
        return self._find_size()

    def find_dtype(self):
        return self.res_dtype


class Call1(VirtualArray):
    def __init__(self, signature, shape, res_dtype, values, order):
        VirtualArray.__init__(self, signature, shape, res_dtype,
                              values.order)
        self.values = values

    def _del_sources(self):
        self.values = None

    def _find_size(self):
        return self.values.find_size()

    def _find_dtype(self):
        return self.res_dtype

    def _eval(self, iter):
        assert isinstance(iter, Call1Iterator)
        val = self.values.eval(iter.child).convert_to(self.res_dtype)
        sig = jit.promote(self.signature)
        assert isinstance(sig, signature.Signature)
        call_sig = sig.components[0]
        assert isinstance(call_sig, signature.Call1)
        return call_sig.func(self.res_dtype, val)

    def start_iter(self):
        if self.forced_result is not None:
            return self.forced_result.start_iter()
        return Call1Iterator(self.values.start_iter())

class Call2(VirtualArray):
    """
    Intermediate class for performing binary operations.
    """
    def __init__(self, signature, shape, calc_dtype, res_dtype, left, right):
        # XXX do something if left.order != right.order
        VirtualArray.__init__(self, signature, shape, res_dtype, left.order)
        self.left = left
        self.right = right
        self.calc_dtype = calc_dtype

    def _del_sources(self):
        self.left = None
        self.right = None

    def _find_size(self):
        try:
            return self.left.find_size()
        except ValueError:
            pass
        return self.right.find_size()

    def start_iter(self):
        if self.forced_result is not None:
            return self.forced_result.start_iter()
        return Call2Iterator(self.left.start_iter(), self.right.start_iter())

    def _eval(self, iter):
        assert isinstance(iter, Call2Iterator)
        lhs = self.left.eval(iter.left).convert_to(self.calc_dtype)
        rhs = self.right.eval(iter.right).convert_to(self.calc_dtype)
        sig = jit.promote(self.signature)
        assert isinstance(sig, signature.Signature)
        call_sig = sig.components[0]
        assert isinstance(call_sig, signature.Call2)
        return call_sig.func(self.calc_dtype, lhs, rhs)

class ViewArray(BaseArray):
    """
    Class for representing views of arrays, they will reflect changes of parent
    arrays. Example: slices
    """
    def __init__(self, parent, signature, shards, backshards, shape):
        self.shards = shards
        self.backshards = backshards
        BaseArray.__init__(self, shape, parent.order)
        self.signature = signature
        self.parent = parent
        self.invalidates = parent.invalidates

    def get_concrete(self):
        # in fact, ViewArray never gets "concrete" as it never stores data.
        # This implementation is needed for BaseArray getitem/setitem to work,
        # can be refactored.
        self.parent.get_concrete()
        return self

    def getitem(self, item):
        return self.parent.getitem(item)

    def eval(self, iter):
        assert isinstance(iter, ViewIterator)
        return self.parent.getitem(iter.offset)

    @unwrap_spec(item=int)
    def setitem_w(self, space, item, w_value):
        return self.parent.setitem_w(space, item, w_value)

    def setitem(self, item, value):
        # This is currently not possible to be called from anywhere.
        raise NotImplementedError

    def descr_len(self, space):
        if self.shape:
            return space.wrap(self.shape[0])
        return space.wrap(1)

class VirtualView(VirtualArray):
    pass

class NDimSlice(ViewArray):
    signature = signature.BaseSignature()

    def __init__(self, parent, signature, start, shards, backshards,
                 shape):
        if isinstance(parent, NDimSlice):
            parent = parent.parent
        ViewArray.__init__(self, parent, signature, shards, backshards, shape)
        self.start = start
        self.size = 1
        for sh in shape:
            self.size *= sh

    def get_root_storage(self):
        return self.parent.get_concrete().get_root_storage()

    def find_size(self):
        return self.size

    def find_dtype(self):
        return self.parent.find_dtype()

    def setslice(self, space, w_value):
        if isinstance(w_value, NDimArray):
            if self.shape != w_value.shape:
                raise OperationError(space.w_TypeError, space.wrap(
                    "wrong assignment"))
        self._sliceloop(w_value)

    def _sliceloop(self, source):
        source_iter = source.start_iter()
        res_iter = self.start_iter()
        while not res_iter.done():
            slice_driver.jit_merge_point(signature=source.signature,
                                         self=self, source=source,
                                         res_iter=res_iter,
                                         source_iter=source_iter)
            self.setitem(res_iter.offset, source.eval(source_iter).convert_to(
                self.find_dtype()))
            source_iter = source_iter.next()
            res_iter = res_iter.next()

    def start_iter(self, offset=0, indices=None):
        return ViewIterator(self, offset=offset, indices=indices)

    def setitem(self, item, value):
        self.parent.setitem(item, value)

    def get_root_shape(self):
        return self.parent.get_root_shape()

class NDimArray(BaseArray):
    """ A class representing contiguous array. We know that each iteration
    by say ufunc will increase the data index by one
    """
    def __init__(self, size, shape, dtype, order='C'):
        BaseArray.__init__(self, shape, order)
        self.size = size
        self.dtype = dtype
        self.storage = dtype.malloc(size)
        self.signature = dtype.signature

    def get_concrete(self):
        return self

    def get_root_storage(self):
        return self.storage

    def find_size(self):
        return self.size

    def find_dtype(self):
        return self.dtype

    def getitem(self, item):
        return self.dtype.getitem(self.storage, item)

    def eval(self, iter):
        assert isinstance(iter, ArrayIterator)
        return self.dtype.getitem(self.storage, iter.offset)

    def descr_len(self, space):
        if len(self.shape):
            return space.wrap(self.shape[0])
        raise OperationError(space.w_TypeError, space.wrap(
            "len() of unsized object"))

    def setitem_w(self, space, item, w_value):
        self.invalidated()
        self.dtype.setitem_w(space, self.storage, item, w_value)

    def setitem(self, item, value):
        self.invalidated()
        self.dtype.setitem(self.storage, item, value)

    def start_iter(self, offset=0, indices=None):
        if self.order == 'C':
            return ArrayIterator(self.size, offset=offset)
        raise NotImplementedError  # use ViewIterator simply, test it

    def __del__(self):
        lltype.free(self.storage, flavor='raw', track_allocation=False)

def zeros(space, w_size, w_dtype=None):
    dtype = space.interp_w(interp_dtype.W_Dtype,
        space.call_function(space.gettypefor(interp_dtype.W_Dtype), w_dtype)
    )
    if space.isinstance_w(w_size, space.w_int):
        size = space.int_w(w_size)
        shape = [size]
    else:
        size = 1
        shape = []
        for w_item in space.fixedview(w_size):
            item = space.int_w(w_item)
            size *= item
            shape.append(item)
    return space.wrap(NDimArray(size, shape[:], dtype=dtype))

@unwrap_spec(size=int)
def ones(space, size, w_dtype=None):
    dtype = space.interp_w(interp_dtype.W_Dtype,
        space.call_function(space.gettypefor(interp_dtype.W_Dtype), w_dtype)
    )

    arr = NDimArray(size, [size], dtype=dtype)
    one = dtype.adapt_val(1)
    arr.dtype.fill(arr.storage, one, 0, size)
    return space.wrap(arr)

BaseArray.typedef = TypeDef(
    'numarray',
    __new__ = interp2app(descr_new_array),


    __len__ = interp2app(BaseArray.descr_len),
    __getitem__ = interp2app(BaseArray.descr_getitem),
    __setitem__ = interp2app(BaseArray.descr_setitem),

    __pos__ = interp2app(BaseArray.descr_pos),
    __neg__ = interp2app(BaseArray.descr_neg),
    __abs__ = interp2app(BaseArray.descr_abs),
    __nonzero__ = interp2app(BaseArray.descr_nonzero),

    __add__ = interp2app(BaseArray.descr_add),
    __sub__ = interp2app(BaseArray.descr_sub),
    __mul__ = interp2app(BaseArray.descr_mul),
    __div__ = interp2app(BaseArray.descr_div),
    __pow__ = interp2app(BaseArray.descr_pow),
    __mod__ = interp2app(BaseArray.descr_mod),

    __radd__ = interp2app(BaseArray.descr_radd),
    __rsub__ = interp2app(BaseArray.descr_rsub),
    __rmul__ = interp2app(BaseArray.descr_rmul),
    __rdiv__ = interp2app(BaseArray.descr_rdiv),
    __rpow__ = interp2app(BaseArray.descr_rpow),
    __rmod__ = interp2app(BaseArray.descr_rmod),

    __eq__ = interp2app(BaseArray.descr_eq),
    __ne__ = interp2app(BaseArray.descr_ne),
    __lt__ = interp2app(BaseArray.descr_lt),
    __le__ = interp2app(BaseArray.descr_le),
    __gt__ = interp2app(BaseArray.descr_gt),
    __ge__ = interp2app(BaseArray.descr_ge),

    __repr__ = interp2app(BaseArray.descr_repr),
    __str__ = interp2app(BaseArray.descr_str),

    dtype = GetSetProperty(BaseArray.descr_get_dtype),
    shape = GetSetProperty(BaseArray.descr_get_shape),

    mean = interp2app(BaseArray.descr_mean),
    sum = interp2app(BaseArray.descr_sum),
    prod = interp2app(BaseArray.descr_prod),
    max = interp2app(BaseArray.descr_max),
    min = interp2app(BaseArray.descr_min),
    argmax = interp2app(BaseArray.descr_argmax),
    argmin = interp2app(BaseArray.descr_argmin),
    all = interp2app(BaseArray.descr_all),
    any = interp2app(BaseArray.descr_any),
    dot = interp2app(BaseArray.descr_dot),

    copy = interp2app(BaseArray.descr_copy),
)
