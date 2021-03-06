__doc__ = '''Multithreaded and thread-safe components.

'''


import collections
import concurrent.futures
import enum
import math
import threading
import time


@enum.unique
class queue_status(enum.IntEnum):
    available = 1
    unavailable = 2
    empty = 3
    not_started = 4


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
        with self._cv:
            task = self._cv.wait_for(self._queue.get)
        if self._need_key:
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
            if status[0] is queue_status.available:
                with self._notify_cv:
                    self._notify_cv.notify_all()
                time.sleep(self._sleep_duration)
            elif status[0] is queue_status.unavailable:
                time.sleep(status[1])
            else:
                time.sleep(self._sleep_duration)


class TaskQueue(object):
    '''A generic thread-safe task queue that supports rate limits.
    Provides rate limiting conservatively rounded to the second.
    '''

    def __init__(self, rate_limits=[], queue_limit=None):
        '''Args:
            rate_limits: a list of (num_requests, num_seconds), where we can
                send a max of num_requests within num_seconds. Default to no
                rate limit.
            queue_limit: maximum size of a queue. Default to unlimited.
        '''
        self._queue = collections.deque()
        self._queue_limit = queue_limit
        self._rate_counters = RateCounterPool(rate_limits)
        self._lock = threading.Lock()

    def put(self, tasks):
        '''Adds as many tasks as possible to the queue, and returns the number
        of tasks added. Thread-safe.
        '''
        with self._lock:
            if self._queue_limit is None:
                self._queue.extend(tasks)
                return len(tasks)
            else:
                truncated = tasks[:self._queue_limit - len(self._queue)]
                self._queue.extend(truncated)
                return len(truncated)

    def status(self):
        '''Returns the status of the queue as the first element. Possibly returns
        the time until a task is available as the second element. Thread-safe.
        '''
        with self._lock:
            now = math.ceil(time.time())
            if self._rate_counters.can_add(now) and len(self._queue) > 0:
                return (queue_status.available,)
            elif len(self._queue) == 0:
                return (queue_status.empty,)
            else:
                ttl = self._rate_counters.time_until_ready(now)
                if ttl is None:
                    return (queue_status.not_started,)
                else:
                    return (queue_status.unavailable, ttl)

    def get(self):
        '''Returns a task iff the caller can execute the task given the time
        limit, else returns None. Thread-safe.
        '''
        with self._lock:
            now = math.ceil(time.time())
            if self._rate_counters.can_add(now) and len(self._queue) > 0:
                self._rate_counters.increment(now)
                task = self._queue.popleft()
                return task


class RateCounterPool(object):
    '''Keeps track of a set of rate limits. Not thread-safe.
    '''

    def __init__(self, rate_limits):
        assert all((len(x) == 2 and x[0] > 0 and x[1] > 0)
                for x in rate_limits), \
                'rate limits must be of type (num_requests, num_seconds).'
        self._rate_counters = [RateCounter(x[0], x[1]) for x in rate_limits]

    def __repr__(self):
        return '\t'.join(x.__repr__() for x in self._rate_counters)

    def can_add(self, now):
        '''Returns True iff a task can be run given the rate limit.'''
        return all(x.can_add(now) for x in self._rate_counters)

    def time_until_ready(self, now):
        '''Returns the time until a task will be ready, in seconds. Returns None
        if uninitialized.
        '''
        ready = max(x.time_until_ready(now) for x in self._rate_counters)
        return ready if ready > 0 else None

    def increment(self, now):
        '''Automatically starts the timer, and adds 1 to the counters.'''
        for x in self._rate_counters:
            x.increment(now)


class RateCounter(object):
    '''Keeps track of one rate limit. Not thread-safe.'''

    def __init__(self, limit, interval, count=0):
        self._limit = limit
        self._interval = interval
        self._count = count
        self._start = None

    def __repr__(self):
        return 'RateCounter(start=%s, next=%s, count=%s, limit=%s)' % \
                (self._start, self._start + self._interval, self._count,
                        self._limit)

    def can_add(self, now):
        '''Returns True iff a task can be run given the rate limit.'''
        self._maybe_reset(now)
        return self._count < self._limit

    def time_until_ready(self, now):
        '''Returns the time until a task is ready, in seconds. Returns None if
        uninitialized.'''
        self._maybe_reset(now)
        if self._start is None or self._count < self._limit:
            return -1
        return self._interval - (now - self._start)

    def increment(self, now):
        '''Automatically starts the timer, and assumes a task will be run soon.
        '''
        if self._start is None:
            self._start = now
        self._maybe_reset(now)
        self._count += 1

    def _maybe_reset(self, now):
        if self._start and now - self._start >= self._interval:
            self._start = now
            self._count = 0


class FunctionalThreadPool(object):
    '''A thread pool that will repeatedly run the same function from multiple
    threads.
    '''

    def __init__(self, fn, num_threads=1):
        '''Args:
            num_threads: number of threads to use. Default to 1.
        '''
        assert num_threads > 0, \
                'Must have at least 1 thread for the Scheduler to run.'
        assert callable(fn), 'function must be callable.'
        self._fn = fn
        self._num_threads = num_threads

    def start(self):
        '''Starts running the thread pool.'''
        def run_forever(f):
            def g():
                while True:
                    f()
            return g

        with concurrent.futures.ThreadPoolExecutor(max_workers=self._num_threads) as executor:
            futures = [executor.submit(run_forever(self._fn))
                    for _ in range(self._num_threads)]
            concurrent.futures.as_completed(futures)
