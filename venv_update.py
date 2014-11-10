#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''\
usage: venv-update [-h] [virtualenv_dir] [requirements [requirements ...]]

Update a (possibly non-existant) virtualenv directory using a requirements.txt listing
When this script completes, the virtualenv should have the same packages as if it were
removed, then rebuilt.

To set the index server, export a PIP_INDEX_SERVER variable.
    See also: http://pip.readthedocs.org/en/latest/user_guide.html#environment-variables

Version control at: https://github.com/yelp/venv-update

positional arguments:
  virtualenv_dir  Destination virtualenv directory (default: virtualenv_run)
  requirements    Requirements files. (default: requirements.txt)

optional arguments:
  -h, --help      show this help message and exit
'''
from __future__ import print_function
from __future__ import unicode_literals

# This script must not rely on anything other than
#   stdlib>=2.6 and virtualenv>1.11
from contextlib import contextmanager
from os import environ


def parseargs(args):
    # TODO: unit test
    if set(args) & set(('-h', '--help')):
        print(__doc__, end='')
        exit(0)

    virtualenv_dir = None
    requirements = []
    remaining = []

    for arg in args:
        if arg.startswith('-'):
            remaining.append(arg)
        elif virtualenv_dir is None:
            virtualenv_dir = arg
        else:
            requirements.append(arg)

    if not virtualenv_dir:
        virtualenv_dir = 'virtualenv_run'
    if not requirements:
        requirements = ['requirements.txt']

    return virtualenv_dir, tuple(requirements), tuple(remaining)


def shellescape(args):
    # TODO: unit test
    from pipes import quote
    return ' '.join(quote(arg) for arg in args)


def colorize(cmd):
    from os import isatty

    if isatty(1):
        template = '\033[01;36m>\033[m \033[01;33m{0}\033[m'
    else:
        template = '> {0}'

    return template.format(shellescape(cmd))


def run(cmd):
    from subprocess import check_call
    check_call(('echo', colorize(cmd)))
    check_call(cmd)


def pip(args):
    """Run pip, in-process."""
    # NOTE: pip *must* be imported here, so that we get the venv's pip
    import pip as pipmodule
    import sys

    # pip<1.6 needs its logging config reset on each invocation, or else we get duplicate outputs -.-
    pipmodule.logger.consumers = []

    sys.stdout.write(colorize(('pip',) + args))
    sys.stdout.write('\n')
    sys.stdout.flush()

    result = pipmodule.main(list(args))
    if result != 0:
        # pip exited with failure, then we should too
        exit(result)


def exec_file(fname, lnames=None, gnames=None):
    """a python3 shim for execfile"""
    with open(fname) as f:
        code = compile(f.read(), fname, 'exec')
        exec(code, lnames, gnames)  # pylint:disable=exec-used


def activate(venv):
    """Activate the virtualenv, in the current python process."""
    # This is the documented way to activate the venv in a python process.
    from os.path import join
    activate_this = join(venv, 'bin', 'activate_this.py')
    exec_file(activate_this, dict(__file__=activate_this))

    # fix up sys.executable as well
    import sys
    sys.executable = join(sys.prefix, 'bin', 'python')


@contextmanager
def active_virtualenv(venv_path):
    """Within this context, the given virtualenv is active.
    All state is restored upon exiting this context
    The given virtualenv should already exist.
    """
    # TODO: unit test
    import sys
    orig_executable = sys.executable
    orig_environ = environ.copy()
    orig_pythonpath = list(sys.path)
    orig_prefix = sys.prefix
    orig_real_prefix = getattr(sys, 'real_prefix', None)

    activate(venv_path)
    yield

    # restore the original environment
    if orig_real_prefix is None:
        del sys.real_prefix  # pylint:disable=no-member
    else:
        sys.real_prefix = orig_real_prefix
    sys.prefix = orig_prefix
    sys.path[:] = orig_pythonpath
    environ.clear()
    environ.update(orig_environ)
    sys.executable = orig_executable


@contextmanager
def clean_venv(venv_path, venv_args):
    """Make a clean virtualenv, and activate it."""
    from os.path import exists
    if exists(venv_path):
        # virtualenv --clear has two problems:
        #   it doesn't properly clear out the venv/bin, causing wacky errors
        #   it writes over (rather than replaces) the python binary, so there's an error if it's in use.
        run(('rm', '-rf', venv_path))

    virtualenv = ('virtualenv', venv_path)
    run(virtualenv + venv_args)

    with active_virtualenv(venv_path):
        yield


def do_install(reqs):
    requirements_as_options = tuple(
        '--requirement={0}'.format(requirement) for requirement in reqs
    )

    # We put the cache in the directory that pip already uses.
    # This has better security characteristics than a machine-wide cache, and is a
    #   pattern people can use for open-source projects
    pip_download_cache = environ['HOME'] + '/.pip/cache'

    environ.update(
        PIP_DOWNLOAD_CACHE=pip_download_cache,
    )

    cache_opts = (
        '--download-cache=' + pip_download_cache,
        '--find-links=file://' + pip_download_cache,
    )

    # --use-wheel is somewhat redundant here, but it means we get an error if we have a bad version of pip/setuptools.
    install = ('install', '--ignore-installed', '--use-wheel') + cache_opts
    wheel = ('wheel',) + cache_opts

    # Bootstrap the install system; setuptools and pip are alreayd installed, just need wheel
    pip(install + ('wheel',))

    # Caching: Make sure everything we want is downloaded, cached, and has a wheel.
    pip(wheel + ('--wheel-dir=' + pip_download_cache, 'wheel') + requirements_as_options)

    # Install: Use our well-populated cache (only) to do the installations.
    # The --ignore-installed gives more-repeatable behavior in the face of --system-site-packages,
    #   and brings us closer to a --no-site-packages future
    pip(install + ('--no-index',) + requirements_as_options)

    return 0


def wait_for_all_subprocesses():
    # TODO: unit-test
    from os import wait
    try:
        while True:
            wait()
    except OSError as error:
        if error.errno == 10:  # no child processes
            return
        else:
            raise


def mark_venv_invalid(venv_path, reqs):
    from os.path import isdir
    if isdir(venv_path):
        print()
        print("Something went wrong! Sending '%s' back in time, so make knows it's invalid." % venv_path)
        print("Waiting for all subprocesses to finish...", end=' ')
        wait_for_all_subprocesses()
        print("DONE")
        run(('touch', venv_path, '--reference', reqs[0], '--date', '1 day ago'))
        print()


def main():
    import sys
    venv_path, reqs, venv_args = parseargs(sys.argv[1:])

    from subprocess import CalledProcessError
    try:
        with clean_venv(venv_path, venv_args):
            exit_code = do_install(reqs)
    except SystemExit as error:
        exit_code = error.code
    except CalledProcessError as error:
        exit_code = error.returncode
    except KeyboardInterrupt:
        exit_code = 1
    except Exception:
        mark_venv_invalid(venv_path, reqs)
        raise

    if exit_code != 0:
        mark_venv_invalid(venv_path, reqs)

    return exit_code


if __name__ == '__main__':
    exit(main())
