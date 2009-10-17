
import autopath
import urllib, urllib2
import subprocess
import sys
import py

BASE = "http://pybench.appspot.com/upload"
MAX_LINES = 10

def upload_results(stderr, url=BASE):
    if stderr.count("\n") > MAX_LINES:
        # trim it a bit
        l = stderr.splitlines()
        stderr = "\n".join(l[len(l) - MAX_LINES:])
    data = urllib.urlencode({'content' : stderr})
    req = urllib2.Request(url, data)
    response = urllib2.urlopen(req)
    response.read()

def run_richards(executable='python'):
    richards = str(py.magic.autopath().dirpath().dirpath().join('goal').join('richards.py'))
    pipe = subprocess.Popen([executable, richards], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    return pipe.communicate()

def main(executable):
    stdout, stderr = run_richards(executable)
    upload_results(stderr)

if __name__ == '__main__':
    if len(sys.argv) == 2:
        executable = sys.argv[1]
    else:
        executable = sys.executable
    main(executable)
