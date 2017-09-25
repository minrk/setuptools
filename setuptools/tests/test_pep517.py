import pytest
import os

# Only test the backend on Python 3
# because we don't want to require
# a concurrent.futures backport for testing
pytest.importorskip('concurrent.futures')

from contextlib import contextmanager
from importlib import import_module
from tempfile import mkdtemp
from concurrent.futures import ProcessPoolExecutor
from .files import build_files
from .textwrap import DALS
from . import contexts


class BuildBackendBase(object):
    def __init__(self, cwd=None, env={}, backend_name='setuptools.pep517'):
        self.cwd = cwd
        self.env = env
        self.backend_name = backend_name


class BuildBackend(BuildBackendBase):
    """PEP 517 Build Backend"""
    def __init__(self, *args, **kwargs):
        super(BuildBackend, self).__init__(*args, **kwargs)
        self.pool = ProcessPoolExecutor()

    def __getattr__(self, name):
        """Handles aribrary function invocations on the build backend."""
        def method(*args, **kw):
            return self.pool.submit(
                BuildBackendCaller(os.path.abspath(self.cwd), self.env,
                                   self.backend_name),
                name, *args, **kw).result()

        return method


class BuildBackendCaller(BuildBackendBase):
    def __call__(self, name, *args, **kw):
        """Handles aribrary function invocations on the build backend."""
        os.chdir(self.cwd)
        os.environ.update(self.env)
        return getattr(import_module(self.backend_name), name)(*args, **kw)


@contextmanager
def enter_directory(dir, val=None):
    while True:
        original_dir = os.getcwd()
        os.chdir(dir)
        yield val
        os.chdir(original_dir)


@pytest.fixture
def build_backend():
    tmpdir = mkdtemp()
    ctx = enter_directory(tmpdir, BuildBackend(cwd='.'))
    with ctx:
        setup_script = DALS("""
        from setuptools import setup

        setup(
            name='foo',
            py_modules=['hello'],
            setup_requires=['six'],
            entry_points={'console_scripts': ['hi = hello.run']},
            zip_safe=False,
        )
        """)

        build_files({
            'setup.py': setup_script,
            'hello.py': DALS("""
                def run():
                    print('hello')
                """)
        })

    return ctx


def test_get_requires_for_build_wheel(build_backend):
    with build_backend as b:
        assert list(sorted(b.get_requires_for_build_wheel())) == \
            list(sorted(['six', 'setuptools', 'wheel']))

def test_build_wheel(build_backend):
    with build_backend as b:
        dist_dir = os.path.abspath('pip-wheel')
        os.makedirs(dist_dir)
        wheel_name = b.build_wheel(dist_dir)

        assert os.path.isfile(os.path.join(dist_dir, wheel_name))


def test_build_sdist(build_backend):
    with build_backend as b:
        dist_dir = os.path.abspath('pip-sdist')
        os.makedirs(dist_dir)
        sdist_name = b.build_sdist(dist_dir)

        assert os.path.isfile(os.path.join(dist_dir, sdist_name))

def test_prepare_metadata_for_build_wheel(build_backend):
    with build_backend as b:
        dist_dir = os.path.abspath('pip-dist-info')
        os.makedirs(dist_dir)

        dist_info = b.prepare_metadata_for_build_wheel(dist_dir)

        assert os.path.isfile(os.path.join(dist_dir, dist_info,
                              'METADATA'))
