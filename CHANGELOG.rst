1.3.1 (2024-02-29)
------------------

* Fix grouping under GitHub actions: print without colors, otherwise the ``::group::`` instructions are not processed.
* When running under GitHub actions, print the ``::endgroup::``  prefix when finishing processing.


1.3.0 (2024-02-28)
------------------

* When running under GitHub actions, add the ``::group::`` prefix to each section header so they are grouped in the GitHub actions logs.

  See `Grouping log lines <https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions#grouping-log-lines>`__ in the GitHub documentation.

* Dropped support for Python 3.6, 3.7, 3.8, and 3.9.


1.2.0 (2021-08-20)
------------------

* `#6 <https://github.com/ESSS/deps/issues/6>`__: Fix ``TypeError`` bug when the ``includes`` entry is defined but is ``None`` in an ``environment.devenv.yml`` file.
* Added support for ``click >=8``.


1.1.0 (2018-09-20)
------------------

* Print some sort of progress in execution headers.


1.0.0 (2018-08-17)
------------------

* Fix bug when used with empty ``devenv.environment.yml`` files.
