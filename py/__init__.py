from initpkg import initpkg 
initpkg(__name__, exportdefs = {
    'path.local':         './path/local/local.LocalPath',
    'path.checker':       './path/common.checker', 
    'path.svnurl':        './path/svn/urlcommand.SvnCommandPath',
    'path.svnwc':         './path/svn/wccommand.SvnWCCommandPath',
    'path.extpy':          './path/extpy/extpy.Extpy',
    'path.NotFound':      './path/error.FileNotFound',
    'path.Denied':        './path/error.PermissionDenied', 
    'path.NoDirectory':   './path/error.NoDirectory', 
    'path.Invalid':       './path/error.Invalid', 

    'test.collect.Collector':  './test/collect.Collector',
    'test.collect.Directory':  './test/collect.Directory',
    'test.collect.Module':     './test/collect.Module',
    'test.collect.PyCollector':'./test/collect.PyCollector',
    'test.collect.Error':      './test/collect.Error',
    'test.run':          './test/run',
    'test.main':         './test/cmdline.main',
    'test.raises':       './test/raises.raises',
    'test.config':       './test/config.config',
    'test.compat.TestCase': './test/compat.TestCase',
    'test.Item':         './test/run.Item', 
    'test.Option':       './test/tool/optparse.Option', 
    'test.TextReporter': './test/report/text/reporter.TextReporter',
    'test.MemoReporter': './test/report/memo.MemoReporter',

    'process.cmdexec':    './process/cmdexec.cmdexec',

    'execnet.PopenGateway': './execnet/register.PopenGateway',
    'execnet.SocketGateway': './execnet/register.SocketGateway', 
    #'execnet.SSHGateway'  : './execnet/register.SSHGateway', 

    'magic.View':         './magic/viewtype.View',
    'magic.autopath':     './magic/autopath.autopath',
    'magic.invoke':       './magic/invoke.invoke',
    'magic.revoke':       './magic/invoke.revoke',
    'magic.AssertionError': './magic/assertion.AssertionError',
    'magic.patch':        './magic/patch.patch',
    'magic.revert':       './magic/patch.revert',
    'magic.dyncode.compile': './magic/dyncode.compile',
    'magic.dyncode.compile2': './magic/dyncode.compile2',
    'magic.dyncode.getsource': './magic/dyncode.getsource',
    'magic.dyncode.tbinfo': './magic/dyncode.tbinfo',
    'magic.dyncode.listtb': './magic/dyncode.listtb',
    'magic.dyncode.findsource': './magic/dyncode.findsource',
    'magic.dyncode.getline': './magic/dyncode.getline',
    'magic.dyncode.getlines': './magic/dyncode.getlines',
})

