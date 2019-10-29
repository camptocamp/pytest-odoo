from setuptools import setup

setup(
    name='pytest-odoo',
    description='py.test plugin to run Odoo tests',
    long_description=open("README.rst").read(),
    use_scm_version=True,
    url='https://github.com/camptocamp/pytest-odoo',
    license='AGPLv3',
    author='Guewen Baconnier',
    author_email='guewen.baconnier@camptocamp.com',
    py_modules=['pytest_odoo'],
    extras_require={
        'autodiscover': ['odoo_autodiscover>=2'],
    },
    entry_points={'pytest11': ['odoo = pytest_odoo']},
    zip_safe=False,
    include_package_data=True,
    platforms='any',
    install_requires=[
        'pytest>=2.9',
    ],
    setup_requires=[
        'setuptools_scm',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Affero General Public License v3',
        'Operating System :: POSIX',
        'Topic :: Software Development :: Testing',
        'Topic :: Software Development :: Libraries',
        'Topic :: Utilities',
        'Programming Language :: Python :: 2.7',
    ]
)
