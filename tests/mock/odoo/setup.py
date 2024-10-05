#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import find_packages, setup

setup(
    name="odoo",
    version="0.0.1",
    packages=find_packages(),
    package_dir={"odoo": "odoo"},
    install_requires="mock"
)
