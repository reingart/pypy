import py

##py.test.skip('In progress at PyCon')

from pypy.rpython.extregistry import EXT_REGISTRY_BY_VALUE, EXT_REGISTRY_BY_TYPE
from pypy.rpython.extregistry import register_value, register_type
from pypy.rpython.extregistry import register_metatype
from pypy.annotation import model as annmodel
from pypy.annotation.annrpython import RPythonAnnotator
from pypy.translator.translator import TranslationContext
from pypy.rpython.lltypesystem import lltype
from pypy.rpython.test.test_llinterp import interpret

def dummy(): 
    raiseNameError

register_value(dummy, compute_result_annotation=annmodel.SomeInteger())

def test_call_dummy():
    def func():
        x = dummy()
        return x
    
    a = RPythonAnnotator()
    s = a.build_types(func, [])
    assert isinstance(s, annmodel.SomeInteger)

def test_callable_annotation():
    def dummy2():
        raiseNameError
    
    def return_annotation():
        return annmodel.SomeInteger()
    
    register_value(dummy2, compute_result_annotation=return_annotation)
    
    def func():
        x = dummy2()
        return x
    
    a = RPythonAnnotator()
    s = a.build_types(func, [])
    assert isinstance(s, annmodel.SomeInteger)
    
def test_register_type_with_callable():
    class DummyType(object):
        pass
    
    dummy_type = DummyType()
    
    def func():
        return dummy_type
    
    def get_annotation(type, instance):
        assert instance is dummy_type
        return annmodel.SomeInteger()
    
    register_type(DummyType, compute_annotation=get_annotation)
    
    a = RPythonAnnotator()
    s = a.build_types(func, [])
    assert isinstance(s, annmodel.SomeInteger)

def test_register_metatype():
    class MetaType(type):
        pass
    
    class RealClass(object):
        __metaclass__ = MetaType
    
    real_class = RealClass()
    
    def func():
        return real_class
    
    def get_annotation(t, x=None):
        assert t is RealClass
        assert x is real_class
        return annmodel.SomeInteger()
    
    register_metatype(MetaType, compute_annotation=get_annotation)
    
    a = RPythonAnnotator()
    s = a.build_types(func, [])
    assert isinstance(s, annmodel.SomeInteger)

def test_register_metatype_2():
    class MetaType(type):
        pass
    
    class RealClass(object):
        __metaclass__ = MetaType
    
    def func(real_class):
        return real_class
    
    def get_annotation(t, x=None):
        assert t is RealClass
        assert x is None
        return annmodel.SomeInteger()
    
    register_metatype(MetaType, compute_annotation=get_annotation)
    
    a = RPythonAnnotator()
    s = a.build_types(func, [RealClass])
    assert isinstance(s, annmodel.SomeInteger)

def test_register_value_with_specialization():
    def dummy_func():
        raiseNameError

    def dummy_specialize(hop):
        return hop.inputconst(lltype.Signed, 42)
    
    register_value(dummy_func, 
        compute_result_annotation=annmodel.SomeInteger(), 
        specialize_call=dummy_specialize)
    
    def func():
        return dummy_func()
    
    res = interpret(func, [])

    assert res == 42
