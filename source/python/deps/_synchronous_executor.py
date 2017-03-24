'''
Helper module to create a synchronous executor to be used replacing the ThreadPoolExecutor
when running synchronously.
'''

from __future__ import unicode_literals


class Future(object):
    def __init__(self, callback, args):
        try:
            self._result = callback(*args)
            self._exception = None
        except Exception as err:
            self._result = None
            self._exception = err
        self.callbacks = []

    def cancelled(self):
        return False

    def cancel(self):
        return False

    def done(self):
        return True

    def exception(self):
        return self._exception

    def result(self):
        if self._exception is not None:
            raise self._exception
        else:
            return self._result

    def add_done_callback(self, callback):
        callback(self)


class SynchronousExecutor:
    """
    Synchronous executor: submit() blocks until it gets the result.
    """
    def submit(self, callback, *args):
        return Future(callback, args)

    def shutdown(self, wait):
        pass
