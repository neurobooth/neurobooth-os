#! /usr/bin/env python
import platform
import os.path as op
import os
import subprocess
import shutil

from setuptools import setup, find_packages

from distutils.command.build_py import build_py
from distutils.cmd import Command

descr = """Code for database management for Neurobooth application."""

DISTNAME = 'neurobooth-os'
DESCRIPTION = descr
MAINTAINER = 'Adonay Nunes'
MAINTAINER_EMAIL = 'adonay.s.nunes@gmail.com'
URL = ''
LICENSE = 'BSD (3-clause)'
DOWNLOAD_URL = 'https://github.com/neurobooth/neurobooth-os'

# Get the version from neurobooth_os/current_config.py — that's the file
# the deploy step (configs/version.bat) overwrites with the real release
# tag. A plain source checkout reads the sentinel "NO VERSION SET".
version = None
with open(os.path.join('neurobooth_os', 'current_config.py'), 'r') as fid:
    for line in (line.strip() for line in fid):
        if line.startswith('version'):
            version = line.split('=')[1].strip().strip('\'').strip('"')
            break
if version is None:
    raise RuntimeError('Could not determine version')


if __name__ == "__main__":
    setup(name=DISTNAME,
          maintainer=MAINTAINER,
          maintainer_email=MAINTAINER_EMAIL,
          description=DESCRIPTION,
          license=LICENSE,
          url=URL,
          version=version,
          download_url=DOWNLOAD_URL,
          long_description=open('README.rst').read(),
          classifiers=[
              'Intended Audience :: Science/Research',
              'Intended Audience :: Developers',
              'License :: OSI Approved',
              'Programming Language :: Python',
              'Topic :: Software Development',
              'Topic :: Scientific/Engineering',
              'Operating System :: Microsoft :: Windows',
              'Operating System :: POSIX',
              'Operating System :: Unix',
              'Operating System :: MacOS',
          ],
          platforms='any',
          install_requires=[
              'pandas'              
          ],
          packages=find_packages(),
          entry_points = {
              'console_scripts': ['neurobooth_os = neurobooth_os.gui:main'],
          }
          )
