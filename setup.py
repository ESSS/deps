import sys

from setuptools import find_packages, setup

other_locals = {}
with open("source/python/deps/version.py") as f:
    exec(f.read(), None, other_locals)
version = other_locals["__version__"]

install_requires = [
    "click",
    "colorama",
    "jinja2",
    "pyyaml",
]

if sys.version_info[0] <= 2:
    # Backport of concurrent.futures
    install_requires.append("futures")

setup(
    name="deps",
    version=version,
    description="A tool to manipulate the dependencies and the project itself",
    author="ESSS",
    author_email="dev@esss.com.br",
    url="https://eden.esss.com.br/stash/projects/ESSS/repos/deps/browse",
    license="MIT",
    packages=find_packages("source/python"),
    package_dir={"": "source/python"},
    entry_points={
        "console_scripts": [
            "deps = deps.deps_cli:main_func",
        ],
    },
    install_requires=install_requires,
    python_requires=">=3.10",
)
