# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

with open('requirements.txt') as f:
	install_requires = f.read().strip().split('\n')

# get version from __version__ variable in vhms_packing/__init__.py
from vhms_packing import __version__ as version

setup(
	name='vhms_packing',
	version=version,
	description='Packing Development',
	author='Fafadia Tech',
	author_email='manan@fafadiatech.com',
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
