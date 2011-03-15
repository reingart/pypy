from pypy.objspace.std.model import registerimplementation, W_Object
from pypy.objspace.std.register_all import register_all
from pypy.objspace.std.multimethod import FailedToImplement
from pypy.interpreter.error import OperationError, operationerrfmt
from pypy.objspace.std.inttype import wrapint
from pypy.objspace.std.listtype import get_list_index
from pypy.objspace.std.sliceobject import W_SliceObject, normalize_simple_slice
from pypy.objspace.std import slicetype
from pypy.interpreter import gateway, baseobjspace
from pypy.rlib.objectmodel import instantiate
from pypy.rlib.listsort import TimSort
from pypy.rlib import rerased
from pypy.interpreter.argument import Signature

def make_range_list(space, start, step, length):
    if length <= 0:
        strategy = space.fromcache(EmptyListStrategy)
        storage = strategy.cast_to_void_star(None)
    else:
        strategy = space.fromcache(RangeListStrategy)
        storage = strategy.cast_to_void_star((start, step, length))
    return W_ListObject.from_storage_and_strategy(space, storage, strategy)

# don't know where to put this function, so it is global for now
def get_strategy_from_list_objects(space, list_w):
    if list_w == []:
        return space.fromcache(EmptyListStrategy)

    # check for ints
    for e in list_w:
        if not is_W_IntObject(e):
            break
        if e is list_w[-1]:
            return space.fromcache(IntegerListStrategy)

    # check for ints
    for e in list_w:
        if not is_W_StringObject(e):
            break
        if e is list_w[-1]:
            return space.fromcache(StringListStrategy)

    return space.fromcache(ObjectListStrategy)

def is_W_IntObject(w_object):
    from pypy.objspace.std.intobject import W_IntObject
    return type(w_object) is W_IntObject

def is_W_StringObject(w_object):
    from pypy.objspace.std.stringobject import W_StringObject
    return type(w_object) is W_StringObject

class W_ListObject(W_Object):
    from pypy.objspace.std.listtype import list_typedef as typedef

    def __init__(w_self, space, wrappeditems):
        assert isinstance(wrappeditems, list)
        w_self.space = space
        w_self.strategy = get_strategy_from_list_objects(space, wrappeditems)
        w_self.strategy.init_from_list_w(w_self, wrappeditems)

    @staticmethod
    def from_storage_and_strategy(space, storage, strategy):
        w_self = instantiate(W_ListObject)
        w_self.space = space
        w_self.strategy = strategy
        w_self.storage = storage
        return w_self

    def __repr__(w_self):
        """ representation for debugging purposes """
        return "%s(%s, %s)" % (w_self.__class__.__name__, w_self.strategy, w_self.storage._content)

    def unwrap(w_list, space):
        # for tests only!
        items = [space.unwrap(w_item) for w_item in w_list.getitems()]
        return list(items)

    def switch_to_object_strategy(self):
        list_w = self.getitems()
        strategy = self.strategy = self.space.fromcache(ObjectListStrategy)
        strategy.init_from_list_w(self, list_w)

    def check_empty_strategy(self):
        if self.length() == 0:
            self.strategy = self.space.fromcache(EmptyListStrategy)
            self.strategy.init_from_list_w(self, [])

    # ___________________________________________________

    def append(w_list, w_item):
        w_list.strategy.append(w_list, w_item)

    def length(self):
        return self.strategy.length(self)

    def getitem(self, index):
        return self.strategy.getitem(self, index)

    def getslice(self, start, stop, step, length):
        return self.strategy.getslice(self, start, stop, step, length)

    def getitems(self):
        return self.strategy.getitems(self)

    # ___________________________________________________

    def inplace_mul(self, times):
        self.strategy.inplace_mul(self, times)

    def deleteitem(self, index):
        self.strategy.deleteitem(self, index)

    def deleteslice(self, start, step, length):
        self.strategy.deleteslice(self, start, step, length)

    def pop(self, index):
        return self.strategy.pop(self, index)

    def setitem(self, index, w_item):
        self.strategy.setitem(self, index, w_item)

    def setslice(self, start, step, slicelength, sequence_w):
        self.strategy.setslice(self, start, step, slicelength, sequence_w)

    def insert(self, index, w_item):
        self.strategy.insert(self, index, w_item)

    def extend(self, items_w):
        self.strategy.extend(self, items_w)

    def reverse(self):
        self.strategy.reverse(self)

registerimplementation(W_ListObject)


class ListStrategy(object):

    def __init__(self, space):
        self.space = space

    def init_from_list_w(self, w_list, list_w):
        raise NotImplementedError

    def length(self, w_list):
        raise NotImplementedError

    def getitem(self, w_list, index):
        raise NotImplementedError

    def getslice(self, w_list, start, stop, step, length):
        raise NotImplementedError

    def getitems(self, w_list):
        raise NotImplementedError

    def append(self, w_list, w_item):
        raise NotImplementedError

    def inplace_mul(self, w_list, times):
        raise NotImplementedError

    def deleteitem(self, w_list, index):
        raise NotImplementedError

    def deleteslice(self, w_list, start, step, slicelength):
        raise NotImplementedError

    def pop(self, w_list, index):
        raise NotImplementedError

    def setitem(self, w_list, index, w_item):
        raise NotImplementedError

    def setslice(self, w_list, start, step, slicelength, sequence_w):
        raise NotImplementedError

    def insert(self, w_list, index, w_item):
        raise NotImplementedError

    def extend(self, w_list, items_w):
        raise NotImplementedError

    def reverse(self, w_list):
        raise NotImplementedError

class EmptyListStrategy(ListStrategy):

    def init_from_list_w(self, w_list, list_w):
        assert len(list_w) == 0
        w_list.storage = self.cast_to_void_star(None)

    cast_to_void_star, cast_from_void_star = rerased.new_erasing_pair("empty")
    cast_to_void_star = staticmethod(cast_to_void_star)
    cast_from_void_star = staticmethod(cast_from_void_star)

    def length(self, w_list):
        return 0

    def getitem(self, w_list, index):
        raise IndexError

    def getslice(self, w_list, start, stop, step, length):
        return W_ListObject(self.space, [])

    def getitems(self, w_list):
        return []

    def append(self, w_list, w_item):
        w_list.__init__(self.space, [w_item])

    def inplace_mul(self, w_list, times):
        return

    def deleteitem(self, w_list, index):
        raise IndexError

    def deleteslice(self, w_list, start, step, slicelength):
        pass

    def pop(self, w_list, index):
        raise IndexError

    def setitem(self, w_list, index, w_item):
        raise IndexError

    def setslice(self, w_list, start, step, slicelength, sequence_w):
        w_list.__init__(self.space, sequence_w)

    def insert(self, w_list, index, w_item):
        assert index == 0
        self.append(w_list, w_item)

    def extend(self, w_list, w_other):
        #XXX items are wrapped and unwrapped again
        w_list.strategy = w_other.strategy
        w_list.strategy.init_from_list_w(w_list, w_other.getitems())

    def reverse(self, w_list):
        pass

class RangeListStrategy(ListStrategy):

    def switch_to_integer_strategy(self, w_list):
        items = self.getitems(w_list, unwrapped=True)
        w_list.strategy = self.space.fromcache(IntegerListStrategy)
        w_list.storage = w_list.strategy.cast_to_void_star(items)

    def wrap(self, intval):
        return self.space.wrap(intval)

    def unwrap(self, w_int):
        return self.space.int_w(w_int)

    def init_from_list_w(self, w_list, list_w):
        raise NotImplementedError

    cast_to_void_star, cast_from_void_star = rerased.new_erasing_pair("range")
    cast_to_void_star = staticmethod(cast_to_void_star)
    cast_from_void_star = staticmethod(cast_from_void_star)

    def length(self, w_list):
        return self.cast_from_void_star(w_list.storage)[2]

    def getitem(self, w_list, i):
        v = self.cast_from_void_star(w_list.storage)
        start = v[0]
        step = v[1]
        length = v[2]
        if i < 0:
            i += length
            if i < 0:
                raise IndexError
        elif i >= length:
            raise IndexError
        return self.wrap(start + i * step)

    def getitems(self, w_list, unwrapped=False):
        l = self.cast_from_void_star(w_list.storage)
        start = l[0]
        step = l[1]
        length  = l[2]
        r = [None] * length

        i = start
        n = 0
        while n < length:
            if unwrapped:
                r[n] = i
            else:
                r[n] = self.wrap(i)
            i += step
            n += 1

        return r

    def getslice(self, w_list, start, stop, step, length):
        v = self.cast_from_void_star(w_list.storage)
        old_start = v[0]
        old_step = v[1]
        old_length = v[2]

        new_start = self.unwrap(w_list.getitem(start))
        new_step = old_step * step
        return make_range_list(self.space, new_start, new_step, length)

    def append(self, w_list, w_item):
        if is_W_IntObject(w_item):
            l = self.cast_from_void_star(w_list.storage)
            step = l[1]
            last_in_range = self.getitem(w_list, -1)
            if self.unwrap(w_item) - step == self.unwrap(last_in_range):
                new = self.cast_to_void_star((l[0],l[1],l[2]+1))
                w_list.storage = new
                return

            self.switch_to_integer_strategy(w_list)
        else:
            w_list.switch_to_object_strategy()
        w_list.append(w_item)

    def inplace_mul(self, w_list, times):
        self.switch_to_integer_strategy(w_list)
        w_list.inplace_mul(times)

    def deleteitem(self, w_list, index):
        self.switch_to_integer_strategy(w_list)
        w_list.deleteitem(index)

    def deleteslice(self, w_list, start, step, slicelength):
        self.switch_to_integer_strategy(w_list)
        w_list.deleteslice(start, step, slicelength)

    def pop(self, w_list, index):
        #XXX move this to list_pop_List_ANY
        if index < 0:
            index += self.length(w_list)

        l = self.cast_from_void_star(w_list.storage)
        if index in [0, self.length(w_list)-1]:
            r = self.getitem(w_list, index)
            if index == 0:
                new = self.cast_to_void_star((l[0]+l[1],l[1],l[2]-1))
            else:
                new = self.cast_to_void_star((l[0],l[1],l[2]-1))
            w_list.storage = new
            w_list.check_empty_strategy()
            return r

        self.switch_to_integer_strategy(w_list)
        return w_list.pop(index)

    def setitem(self, w_list, index, w_item):
        self.switch_to_integer_strategy(w_list)
        w_list.setitem(index, w_item)

    def setslice(self, w_list, start, step, slicelength, sequence_w):
        self.switch_to_integer_strategy(w_list)
        w_list.setslice(start, step, slicelength)

    def insert(self, w_list, index, w_item):
        self.switch_to_integer_strategy(w_list)
        w_list.insert(index, w_item)

    def extend(self, w_list, items_w):
        self.switch_to_integer_strategy(w_list)
        w_list.extend(items_w)

    def reverse(self, w_list):
        v = self.cast_from_void_star(w_list.storage)
        last = w_list.getitem(-1) #XXX wrapped
        length = v[2]
        skip = v[1]
        new = self.cast_to_void_star((self.unwrap(last), -skip, length))
        w_list.storage = new

class AbstractUnwrappedStrategy(object):
    _mixin_ = True

    def wrap(self, unwrapped):
        raise NotImplementedError

    def unwrap(self, wrapped):
        raise NotImplementedError

    @staticmethod
    def cast_from_void_star(storage):
        raise NotImplementedError("abstract base class")

    @staticmethod
    def cast_to_void_star(obj):
        raise NotImplementedError("abstract base class")

    def is_correct_type(self, w_obj):
        raise NotImplementedError("abstract base class")

    def list_is_correct_type(self, w_list):
        raise NotImplementedError("abstract base class")

    def init_from_list_w(self, w_list, list_w):
        l = [self.unwrap(w_item) for w_item in list_w]
        w_list.storage = self.cast_to_void_star(l)

    def length(self, w_list):
        return len(self.cast_from_void_star(w_list.storage))

    def getitem(self, w_list, index):
        try:
            return self.wrap(self.cast_from_void_star(w_list.storage)[index])
        except IndexError: # make RPython raise the exception
            raise

    def getitems(self, w_list):
        return [self.wrap(item) for item in self.cast_from_void_star(w_list.storage)]

    def getslice(self, w_list, start, stop, step, length):
        if step == 1:
            l = self.cast_from_void_star(w_list.storage)
            assert stop >= 0
            sublist = l[start:stop]
            storage = self.cast_to_void_star(sublist)
            return W_ListObject.from_storage_and_strategy(self.space, storage, self)
        else:
            subitems_w = [None] * length
            for i in range(length):
                subitems_w[i] = w_list.getitem(start)
                start += step
            return W_ListObject(self.space, subitems_w)

    def append(self,  w_list, w_item):

        if self.is_correct_type(w_item):
            self.cast_from_void_star(w_list.storage).append(self.unwrap(w_item))
            return

        w_list.switch_to_object_strategy()
        w_list.append(w_item)

    def insert(self, w_list, index, w_item):
        l = self.cast_from_void_star(w_list.storage)

        if self.is_correct_type(w_item):
            l.insert(index, self.unwrap(w_item))
            return

        w_list.switch_to_object_strategy()
        w_list.insert(index, w_item)

    def extend(self, w_list, w_other):
        l = self.cast_from_void_star(w_list.storage)
        if self.list_is_correct_type(w_other):
            l += self.cast_from_void_star(w_other.storage)
            return

        #XXX unnecessary copy if w_other is ObjectList
        list_w = w_other.getitems()
        w_other = W_ListObject(self.space, list_w)
        w_other.switch_to_object_strategy()

        w_list.switch_to_object_strategy()
        w_list.extend(w_other)

    def setitem(self, w_list, index, w_item):
        l = self.cast_from_void_star(w_list.storage)

        if self.is_correct_type(w_item):
            l[index] = self.unwrap(w_item)
            return

        w_list.switch_to_object_strategy()
        w_list.setitem(index, w_item)

    def setslice(self, w_list, start, step, slicelength, sequence_w):
        #XXX inefficient
        assert slicelength >= 0
        items = self.cast_from_void_star(w_list.storage)

        if (self is not self.space.fromcache(ObjectListStrategy) and
                not self.list_is_correct_type(W_ListObject(self.space, sequence_w)) and
                len(sequence_w) != 0):
            w_list.switch_to_object_strategy()
            w_list.setslice(start, step, slicelength, sequence_w)
            return

        oldsize = len(items)
        len2 = len(sequence_w)
        if step == 1:  # Support list resizing for non-extended slices
            delta = slicelength - len2
            if delta < 0:
                delta = -delta
                newsize = oldsize + delta
                # XXX support this in rlist!
                items += [None] * delta
                lim = start+len2
                i = newsize - 1
                while i >= lim:
                    items[i] = items[i-delta]
                    i -= 1
            elif start >= 0:
                del items[start:start+delta]
            else:
                assert delta==0   # start<0 is only possible with slicelength==0
        elif len2 != slicelength:  # No resize for extended slices
            raise operationerrfmt(space.w_ValueError, "attempt to "
                  "assign sequence of size %d to extended slice of size %d",
                  len2, slicelength)

        if sequence_w is items:
            if step > 0:
                # Always copy starting from the right to avoid
                # having to make a shallow copy in the case where
                # the source and destination lists are the same list.
                i = len2 - 1
                start += i*step
                while i >= 0:
                    items[start] = self.unwrap(sequence_w[i])
                    start -= step
                    i -= 1
                return
            else:
                # Make a shallow copy to more easily handle the reversal case
                # XXX why is this needed ???
                sequence_w = list(sequence_w)
        for i in range(len2):
            items[start] = self.unwrap(sequence_w[i])
            start += step

    def deleteitem(self, w_list, index):
        l = self.cast_from_void_star(w_list.storage)
        del l[index]
        w_list.check_empty_strategy()

    def deleteslice(self, w_list, start, step, slicelength):
        items = self.cast_from_void_star(w_list.storage)
        if slicelength==0:
            return

        if step < 0:
            start = start + step * (slicelength-1)
            step = -step

        if step == 1:
            assert start >= 0
            assert slicelength >= 0
            del items[start:start+slicelength]
        else:
            n = len(items)
            i = start

            for discard in range(1, slicelength):
                j = i+1
                i += step
                while j < i:
                    items[j-discard] = items[j]
                    j += 1

            j = i+1
            while j < n:
                items[j-slicelength] = items[j]
                j += 1
            start = n - slicelength
            assert start >= 0 # annotator hint
            del items[start:]

        w_list.check_empty_strategy()

    def pop(self, w_list, index):
        l = self.cast_from_void_star(w_list.storage)
        w_item = self.wrap(l.pop(index))

        w_list.check_empty_strategy()
        return w_item

    def inplace_mul(self, w_list, times):
        l = self.cast_from_void_star(w_list.storage)
        l *= times

    def reverse(self, w_list):
        self.cast_from_void_star(w_list.storage).reverse()

class ObjectListStrategy(AbstractUnwrappedStrategy, ListStrategy):
    def unwrap(self, w_obj):
        return w_obj

    def wrap(self, item):
        return item

    cast_to_void_star, cast_from_void_star = rerased.new_erasing_pair("object")
    cast_to_void_star = staticmethod(cast_to_void_star)
    cast_from_void_star = staticmethod(cast_from_void_star)

    def is_correct_type(self, w_obj):
        return True

    def list_is_correct_type(self, w_list):
        return w_list.strategy is self.space.fromcache(ObjectListStrategy)

    def init_from_list_w(self, w_list, list_w):
        w_list.storage = self.cast_to_void_star(list_w)

    # XXX implement getitems without copying here

class IntegerListStrategy(AbstractUnwrappedStrategy, ListStrategy):

    def wrap(self, intval):
        return self.space.wrap(intval)

    def unwrap(self, w_int):
        return self.space.int_w(w_int)

    cast_to_void_star, cast_from_void_star = rerased.new_erasing_pair("integer")
    cast_to_void_star = staticmethod(cast_to_void_star)
    cast_from_void_star = staticmethod(cast_from_void_star)

    def is_correct_type(self, w_obj):
        return is_W_IntObject(w_obj)

    def list_is_correct_type(self, w_list):
        return w_list.strategy is self.space.fromcache(IntegerListStrategy)

class StringListStrategy(AbstractUnwrappedStrategy, ListStrategy):

    def wrap(self, stringval):
        return self.space.wrap(stringval)

    def unwrap(self, w_string):
        return self.space.str_w(w_string)

    cast_to_void_star, cast_from_void_star = rerased.new_erasing_pair("string")
    cast_to_void_star = staticmethod(cast_to_void_star)
    cast_from_void_star = staticmethod(cast_from_void_star)

    def is_correct_type(self, w_obj):
        return is_W_StringObject(w_obj)

    def list_is_correct_type(self, w_list):
        return w_list.strategy is self.space.fromcache(StringListStrategy)

# _______________________________________________________

init_signature = Signature(['sequence'], None, None)
init_defaults = [None]

def init__List(space, w_list, __args__):
    # this is on the silly side
    w_iterable, = __args__.parse_obj(
            None, 'list', init_signature, init_defaults)
    #
    # this is the old version of the loop at the end of this function:
    #
    #   w_list.wrappeditems = space.unpackiterable(w_iterable)
    #
    # This is commented out to avoid assigning a new RPython list to
    # 'wrappeditems', which defeats the W_FastSeqIterObject optimization.
    #
    w_list.__init__(space, [])
    if w_iterable is not None:
        w_iterator = space.iter(w_iterable)
        while True:
            try:
                w_item = space.next(w_iterator)
            except OperationError, e:
                if not e.match(space, space.w_StopIteration):
                    raise
                break  # done
            #items_w.append(w_item)
            w_list.append(w_item)

def len__List(space, w_list):
    result = w_list.length()
    return wrapint(space, result)

def getitem__List_ANY(space, w_list, w_index):
    try:
        return w_list.getitem(get_list_index(space, w_index))
    except IndexError:
        raise OperationError(space.w_IndexError,
                             space.wrap("list index out of range"))

def getitem__List_Slice(space, w_list, w_slice):
    # XXX consider to extend rlist's functionality?
    length = w_list.length()
    start, stop, step, slicelength = w_slice.indices4(space, length)
    assert slicelength >= 0
    return w_list.getslice(start, stop, step, slicelength)

def getslice__List_ANY_ANY(space, w_list, w_start, w_stop):
    length = w_list.length()
    start, stop = normalize_simple_slice(space, length, w_start, w_stop)
    return w_list.getslice(start, stop, 1, stop - start)

def setslice__List_ANY_ANY_ANY(space, w_list, w_start, w_stop, w_iterable):
    length = w_list.length()
    start, stop = normalize_simple_slice(space, length, w_start, w_stop)
    sequence_w = space.listview(w_iterable)
    w_list.setslice(start, 1, stop-start, sequence_w)

def delslice__List_ANY_ANY(space, w_list, w_start, w_stop):
    length = w_list.length()
    start, stop = normalize_simple_slice(space, length, w_start, w_stop)
    w_list.deleteslice(start, 1, stop-start)

def contains__List_ANY(space, w_list, w_obj):
    # needs to be safe against eq_w() mutating the w_list behind our back
    i = 0
    while i < w_list.length(): # intentionally always calling len!
        if space.eq_w(w_list.getitem(i), w_obj):
            return space.w_True
        i += 1
    return space.w_False

def iter__List(space, w_list):
    from pypy.objspace.std import iterobject
    return iterobject.W_FastListIterObject(w_list)

def add__List_List(space, w_list1, w_list2):
    return W_ListObject(space, w_list1.getitems() + w_list2.getitems())


def inplace_add__List_ANY(space, w_list1, w_iterable2):
    list_extend__List_ANY(space, w_list1, w_iterable2)
    return w_list1

def inplace_add__List_List(space, w_list1, w_list2):
    list_extend__List_List(space, w_list1, w_list2)
    return w_list1

def mul_list_times(space, w_list, w_times):
    try:
        times = space.getindex_w(w_times, space.w_OverflowError)
    except OperationError, e:
        if e.match(space, space.w_TypeError):
            raise FailedToImplement
        raise
    return W_ListObject(space, w_list.getitems() * times)

def mul__List_ANY(space, w_list, w_times):
    return mul_list_times(space, w_list, w_times)

def mul__ANY_List(space, w_times, w_list):
    return mul_list_times(space, w_list, w_times)

def inplace_mul__List_ANY(space, w_list, w_times):
    try:
        times = space.getindex_w(w_times, space.w_OverflowError)
    except OperationError, e:
        if e.match(space, space.w_TypeError):
            raise FailedToImplement
        raise
    w_list.inplace_mul(times)
    return w_list

def eq__List_List(space, w_list1, w_list2):
    # needs to be safe against eq_w() mutating the w_lists behind our back
    items1_w = w_list1.getitems()
    items2_w = w_list2.getitems()
    return equal_wrappeditems(space, items1_w, items2_w)

def equal_wrappeditems(space, items1_w, items2_w):
    if len(items1_w) != len(items2_w):
        return space.w_False
    i = 0
    while i < len(items1_w) and i < len(items2_w):
        if not space.eq_w(items1_w[i], items2_w[i]):
            return space.w_False
        i += 1
    return space.w_True

def lessthan_unwrappeditems(space, items1_w, items2_w):
    # needs to be safe against eq_w() mutating the w_lists behind our back
    # Search for the first index where items are different
    i = 0
    while i < len(items1_w) and i < len(items2_w):
        w_item1 = items1_w[i]
        w_item2 = items2_w[i]
        if not space.eq_w(w_item1, w_item2):
            return space.lt(w_item1, w_item2)
        i += 1
    # No more items to compare -- compare sizes
    return space.newbool(len(items1_w) < len(items2_w))

def greaterthan_unwrappeditems(space, items1_w, items2_w):
    # needs to be safe against eq_w() mutating the w_lists behind our back
    # Search for the first index where items are different
    i = 0
    while i < len(items1_w) and i < len(items2_w):
        w_item1 = items1_w[i]
        w_item2 = items2_w[i]
        if not space.eq_w(w_item1, w_item2):
            return space.gt(w_item1, w_item2)
        i += 1
    # No more items to compare -- compare sizes
    return space.newbool(len(items1_w) > len(items2_w))

def lt__List_List(space, w_list1, w_list2):
    return lessthan_unwrappeditems(space, w_list1.getitems(),
        w_list2.getitems())

def gt__List_List(space, w_list1, w_list2):
    return greaterthan_unwrappeditems(space, w_list1.getitems(),
        w_list2.getitems())

def delitem__List_ANY(space, w_list, w_idx):
    idx = get_list_index(space, w_idx)
    try:
        w_list.deleteitem(idx)
    except IndexError:
        raise OperationError(space.w_IndexError,
                             space.wrap("list deletion index out of range"))
    return space.w_None


def delitem__List_Slice(space, w_list, w_slice):
    start, stop, step, slicelength = w_slice.indices4(space, w_list.length())
    w_list.deleteslice(start, step, slicelength)

def setitem__List_ANY_ANY(space, w_list, w_index, w_any):
    idx = get_list_index(space, w_index)
    try:
        w_list.setitem(idx, w_any)
    except IndexError:
        raise OperationError(space.w_IndexError,
                             space.wrap("list index out of range"))
    return space.w_None

def setitem__List_Slice_ANY(space, w_list, w_slice, w_iterable):
    oldsize = w_list.length()
    start, stop, step, slicelength = w_slice.indices4(space, oldsize)
    sequence_w = space.listview(w_iterable)
    w_list.setslice(start, step, slicelength, sequence_w)

app = gateway.applevel("""
    def listrepr(currently_in_repr, l):
        'The app-level part of repr().'
        list_id = id(l)
        if list_id in currently_in_repr:
            return '[...]'
        currently_in_repr[list_id] = 1
        try:
            return "[" + ", ".join([repr(x) for x in l]) + ']'
        finally:
            try:
                del currently_in_repr[list_id]
            except:
                pass
""", filename=__file__)

listrepr = app.interphook("listrepr")

def repr__List(space, w_list):
    if w_list.length() == 0:
        return space.wrap('[]')
    ec = space.getexecutioncontext()
    w_currently_in_repr = ec._py_repr
    if w_currently_in_repr is None:
        w_currently_in_repr = ec._py_repr = space.newdict()
    return listrepr(space, w_currently_in_repr, w_list)

def list_insert__List_ANY_ANY(space, w_list, w_where, w_any):
    where = space.int_w(w_where)
    length = w_list.length()
    index = get_positive_index(where, length)
    w_list.insert(index, w_any)
    return space.w_None

def get_positive_index(where, length):
    if where < 0:
        where += length
        if where < 0:
            where = 0
    elif where > length:
        where = length
    return where

def list_append__List_ANY(space, w_list, w_any):
    w_list.append(w_any)
    return space.w_None

def list_extend__List_List(space, w_list, w_other):
    w_list.extend(w_other)
    return space.w_None

def list_extend__List_ANY(space, w_list, w_any):
    w_other = W_ListObject(space, space.listview(w_any))
    w_list.extend(w_other)
    return space.w_None

# note that the default value will come back wrapped!!!
def list_pop__List_ANY(space, w_list, w_idx=-1):
    if w_list.length() == 0:
        raise OperationError(space.w_IndexError,
                             space.wrap("pop from empty list"))
    idx = space.int_w(w_idx)
    try:
        return w_list.pop(idx)
    except IndexError:
        raise OperationError(space.w_IndexError,
                             space.wrap("pop index out of range"))

def list_remove__List_ANY(space, w_list, w_any):
    # needs to be safe against eq_w() mutating the w_list behind our back
    i = 0
    while i < w_list.length():
        if space.eq_w(w_list.getitem(i), w_any):
            if i < w_list.length(): # if this is wrong the list was changed
                w_list.deleteitem(i)
            return space.w_None
        i += 1
    raise OperationError(space.w_ValueError,
                         space.wrap("list.remove(x): x not in list"))

def list_index__List_ANY_ANY_ANY(space, w_list, w_any, w_start, w_stop):
    # needs to be safe against eq_w() mutating the w_list behind our back
    size = w_list.length()
    i = slicetype.adapt_bound(space, size, w_start)
    stop = slicetype.adapt_bound(space, size, w_stop)
    while i < stop and i < w_list.length():
        if space.eq_w(w_list.getitem(i), w_any):
            return space.wrap(i)
        i += 1
    raise OperationError(space.w_ValueError,
                         space.wrap("list.index(x): x not in list"))

def list_count__List_ANY(space, w_list, w_any):
    # needs to be safe against eq_w() mutating the w_list behind our back
    count = 0
    i = 0
    while i < w_list.length():
        if space.eq_w(w_list.getitem(i), w_any):
            count += 1
        i += 1
    return space.wrap(count)

def list_reverse__List(space, w_list):
    w_list.reverse()
    return space.w_None

# ____________________________________________________________
# Sorting

# Reverse a slice of a list in place, from lo up to (exclusive) hi.
# (used in sort)

class KeyContainer(baseobjspace.W_Root):
    def __init__(self, w_key, w_item):
        self.w_key = w_key
        self.w_item = w_item

# NOTE: all the subclasses of TimSort should inherit from a common subclass,
#       so make sure that only SimpleSort inherits directly from TimSort.
#       This is necessary to hide the parent method TimSort.lt() from the
#       annotator.
class SimpleSort(TimSort):
    def lt(self, a, b):
        space = self.space
        return space.is_true(space.lt(a, b))

class CustomCompareSort(SimpleSort):
    def lt(self, a, b):
        space = self.space
        w_cmp = self.w_cmp
        w_result = space.call_function(w_cmp, a, b)
        try:
            result = space.int_w(w_result)
        except OperationError, e:
            if e.match(space, space.w_TypeError):
                raise OperationError(space.w_TypeError,
                    space.wrap("comparison function must return int"))
            raise
        return result < 0

class CustomKeySort(SimpleSort):
    def lt(self, a, b):
        assert isinstance(a, KeyContainer)
        assert isinstance(b, KeyContainer)
        space = self.space
        return space.is_true(space.lt(a.w_key, b.w_key))

class CustomKeyCompareSort(CustomCompareSort):
    def lt(self, a, b):
        assert isinstance(a, KeyContainer)
        assert isinstance(b, KeyContainer)
        return CustomCompareSort.lt(self, a.w_key, b.w_key)

def list_sort__List_ANY_ANY_ANY(space, w_list, w_cmp, w_keyfunc, w_reverse):
    #XXX so far sorting always wraps list
    has_cmp = not space.is_w(w_cmp, space.w_None)
    has_key = not space.is_w(w_keyfunc, space.w_None)
    has_reverse = space.is_true(w_reverse)

    # create and setup a TimSort instance
    if has_cmp:
        if has_key:
            sorterclass = CustomKeyCompareSort
        else:
            sorterclass = CustomCompareSort
    else:
        if has_key:
            sorterclass = CustomKeySort
        else:
            sorterclass = SimpleSort
    sorter = sorterclass(w_list.getitems(), w_list.length())
    sorter.space = space
    sorter.w_cmp = w_cmp

    try:
        # The list is temporarily made empty, so that mutations performed
        # by comparison functions can't affect the slice of memory we're
        # sorting (allowing mutations during sorting is an IndexError or
        # core-dump factory, since wrappeditems may change).
        w_list.__init__(space, [])

        # wrap each item in a KeyContainer if needed
        if has_key:
            for i in range(sorter.listlength):
                w_item = sorter.list[i]
                w_key = space.call_function(w_keyfunc, w_item)
                sorter.list[i] = KeyContainer(w_key, w_item)

        # Reverse sort stability achieved by initially reversing the list,
        # applying a stable forward sort, then reversing the final result.
        if has_reverse:
            sorter.list.reverse()

        # perform the sort
        sorter.sort()

        # reverse again
        if has_reverse:
            sorter.list.reverse()

    finally:
        # unwrap each item if needed
        if has_key:
            for i in range(sorter.listlength):
                w_obj = sorter.list[i]
                if isinstance(w_obj, KeyContainer):
                    sorter.list[i] = w_obj.w_item

        # check if the user mucked with the list during the sort
        mucked = w_list.length() > 0

        # put the items back into the list
        w_list.__init__(space, sorter.list)

    if mucked:
        raise OperationError(space.w_ValueError,
                             space.wrap("list modified during sort"))

    return space.w_None


from pypy.objspace.std import listtype
register_all(vars(), listtype)
