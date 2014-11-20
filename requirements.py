#!/usr/bin/env python
from __future__ import unicode_literals
from __future__ import print_function
from pip.req import parse_requirements


def pip_get_installed():
    from pip._vendor.pkg_resources import working_set
    from pip.util import get_installed_distributions
    import pip

    dependency_links = []

    for dist in working_set:
        if dist.has_metadata('dependency_links.txt'):
            dependency_links.extend(
                dist.get_metadata_lines('dependency_links.txt')
            )

    installed = {}
    for dist in get_installed_distributions(local_only=True):
        req = pip.FrozenRequirement.from_dist(
            dist,
            dependency_links,
        )

        installed[req.name] = req.req

    return installed


def action(curr, next):  # pylint:disable=redefined-builtin
    print('%s -> %s' % (curr, next))

    if next is None:
        if curr is None:
            print('=')
        else:
            print('U')
    elif curr is None:
        print('I')
    elif curr == next:
        print('=')
    else:
        print('I')


def print_all_logging():
    from sys import stdout
    from pip.log import logger
    logger.add_consumers(
        (logger.NOTIFY, stdout)
    )


def print_all_logging_16():
    import logging
    import sys

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    root.addHandler(ch)


def main():
    print_all_logging()

    required = {}
    strange = []
    for req in parse_requirements('requirements.txt'):
        if req.url or req.editable:
            strange.append(req)
        elif req.req:
            required[req.req.key] = req.req
        else:
            raise ValueError('Unexpected requirement format: %r' % vars(req))

    print('STRANGE:')
    for req in strange:
        print(req)


    from pip.commands.install import InstallCommand
    install = InstallCommand()
    installed = install.run(
        *install.parse_args(
            [req.url for req in strange]
        )
    )
    print(installed)
    if isinstance(installed, int):
        return installed

    url_installed = set(installed.requirements.keys())


    from pprint import pprint
    pprint(required)
    installed = pip_get_installed()

    for req in url_installed:
        print('installed by url:', req)
        required.pop(req, None)
        installed.pop(req, None)

    pprint(installed)

    packages = sorted(set(installed).union(required))
    for package in packages:
        print('%s: ' % package, end='')

        req = required.get(package)
        ins = installed.get(package)
        action(ins, req)

    # wheel the I's
    # install  the I's
    # remove the installed.requirements.keys() from the U's
    # uninstall the U's

if __name__ == '__main__':
    exit(main())
