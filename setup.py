from setuptools import setup, find_packages
setup(
    name='deps',
    version='0.5',
    description='A tool to manipulate the dependencies and the project itself',
    author='ESSS',
    author_email='dev@esss.com.br',
    url='https://eden.esss.com.br/stash/projects/ESSS/repos/deps/browse',
    packages=find_packages('source/python'),
    package_dir={'':'source/python'},
    entry_points={
        'console_scripts': [
            'deps = deps.deps_cli:main_func',
        ],
    },
    install_requires=[
      'click',
      'colorama',
      'jinja2',
      'pyyaml',
    ],
)
