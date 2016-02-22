__doc__ = '''Interface for rate-limited API tasks.

'''


import threading
import time

from lol.network import queue_status, TaskQueue, FunctionalThreadPool


class APITaskQueue(object):
    '''Rate-limited multi-threaded API task queue.'''

    def __init__(self, api_keys=[], rate_limits=[], queue_limit=None,
            num_threads=1):
        '''Args:
            api_keys: if this is set, a key will be passed onto the task as a
                param.
            rate_limits: a list of (num_requests, num_seconds), where we can
                send a max of num_requests within num_seconds for each key.
            queue_limit: maximum number of tasks we should enqueue. Default to
                unlimited.
            num_threads: number of threads to use. Default to 1.
        '''
        assert all((len(x) == 2 and x[0] > 0 and x[1] > 0) for x in rate_limits), \
                'rate limits must be of type (num_requests, num_seconds).'

        # Scale up the rate limits
        if len(api_keys) > 1:
            for i in range(len(rate_limits)):
                rate_limits[i] = (rate_limits[i][0] * len(api_keys),
                        rate_limits[i][1])

        self._queue = TaskQueue(rate_limits=rate_limits, queue_limit=queue_limit)
        self._thread_pool = FunctionalThreadPool(self._check_and_run,
                num_threads=num_threads)

        self._api_keys = api_keys
        self._need_key = len(api_keys) > 0
        if self._need_key:
            self._key_counter = 0
            self._key_lock = threading.Lock()
        self._cv = threading.Condition()

    def put(self, tasks):
        '''Adds tasks to the queue. Thread-safe.'''
        return self._queue.put(tasks)

    def start(self):
        '''Activates the scheduler. Queue should be seeded before running this.
        '''
        PeekQueueThread(self._queue, self._cv).start()
        self._thread_pool.start()

    def _check_and_run(self):
        task = None
        with self._cv:
            task = self._cv.wait_for(self._queue.get)
        if self._need_key:
            key = None
            with self._key_lock:
                key = self._api_keys[self._key_counter]
                self._key_counter = (self._key_counter + 1) % len(self._api_keys)
            task(key=key)
        else:
            task()


class PeekQueueThread(threading.Thread):
    '''Thread that occasionally checks if there is something in the queue.'''

    def __init__(self, queue, notify_cv, sleep_duration=0.5):
        super().__init__()
        self._queue = queue
        self._notify_cv = notify_cv
        self._sleep_duration = sleep_duration

    def run(self):
        '''Override.'''
        while True:
            status = self._queue.status()
            print('STATUS', status)
            if status[0] is queue_status.available:
                with self._notify_cv:
                    self._notify_cv.notify_all()
                time.sleep(self._sleep_duration)
            elif status[0] is queue_status.unavailable:
                time.sleep(status[1])
            else:
                time.sleep(self._sleep_duration)


class Task(object):
    '''A task that can capture a context, and be called.'''

    def __init__(self, fn, **kwargs):
        self._fn = fn
        self._kwargs = kwargs

    def __call__(self, **kwargs):
        self._fn(**{**kwargs, **self._kwargs})


def make_task(f, **kwargs):
    return Task(f, **kwargs)
