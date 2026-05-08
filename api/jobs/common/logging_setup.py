# jobs/common/logging_setup.py
import os
import time
import asyncio
import inspect
import threading
import logging
import logging.handlers
from queue import Queue, Empty


class ProgramLogger(logging.Logger):
    def __init__(self, name, program_name="easypaisa", level=logging.NOTSET):
        super().__init__(name, level)
        self.program_name = program_name

    def _log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, stacklevel=1):
        frame = inspect.currentframe()
        for _ in range(3):
            if frame is not None:
                frame = frame.f_back
        func_name = frame.f_code.co_name if frame is not None else 'unknown'
        msg = f"[{self.program_name}][{func_name}] {msg}"
        super()._log(level, msg, args, exc_info, extra, stack_info, stacklevel)


class TraceIDFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self._local = threading.local()

    @property
    def trace_id(self):
        return getattr(self._local, 'trace_id', 'default')

    @trace_id.setter
    def trace_id(self, value):
        self._local.trace_id = value

    def filter(self, record):
        record.trace_id = self.trace_id
        try:
            task = asyncio.current_task()
            if task:
                record.task_id = f"task_{id(task) % 10000:04d}"
            else:
                record.task_id = "sync"
        except RuntimeError:
            record.task_id = "sync"
        return True


class BufferedFileHandler(logging.handlers.TimedRotatingFileHandler):
    def __init__(self, filename, when='midnight', interval=1, backupCount=10,
                 encoding='utf-8', delay=True, buffer_size=8192, flush_interval=5.0):
        super().__init__(filename, when, interval, backupCount, encoding, delay)
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        self.buffer = []
        self.buffer_bytes = 0
        self.last_flush_time = time.time()
        self._buffer_lock = threading.Lock()
        self._start_flush_timer()

    def _start_flush_timer(self):
        def flush_timer():
            while True:
                time.sleep(self.flush_interval)
                with self._buffer_lock:
                    if self.buffer and (time.time() - self.last_flush_time) >= self.flush_interval:
                        self._force_flush()
        timer_thread = threading.Thread(target=flush_timer, daemon=True)
        timer_thread.start()

    def emit(self, record):
        try:
            with self._buffer_lock:
                msg = self.format(record)
                msg_bytes = len(msg.encode('utf-8'))
                self.buffer.append(msg + '\n')
                self.buffer_bytes += msg_bytes
                if self._should_flush():
                    self._force_flush()
        except Exception:
            self.handleError(record)

    def _should_flush(self):
        if self.buffer_bytes >= self.buffer_size:
            return True
        if time.time() - self.last_flush_time >= self.flush_interval:
            return True
        if len(self.buffer) >= 1000:
            return True
        return False

    def _force_flush(self):
        if not self.buffer:
            return
        try:
            if self.stream is None:
                self.stream = self._open()
            for log_line in self.buffer:
                self.stream.write(log_line)
            self.flush()
            self.buffer.clear()
            self.buffer_bytes = 0
            self.last_flush_time = time.time()
        except Exception:
            pass

    def flush(self):
        if self.stream:
            self.stream.flush()

    def close(self):
        with self._buffer_lock:
            self._force_flush()
        super().close()


class AsyncBatchLogHandler(logging.Handler):
    def __init__(self, target_handler, batch_size=100, flush_interval=2.0, max_queue_size=10000):
        super().__init__()
        self.target_handler = target_handler
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.max_queue_size = max_queue_size
        self.log_queue = Queue(maxsize=max_queue_size)
        self.running = True
        self.worker_thread = None
        self.stats = {'total_logs': 0, 'batches_written': 0, 'queue_full_drops': 0}
        self._start_worker()

    def _start_worker(self):
        def worker():
            batch = []
            last_flush_time = time.time()
            while self.running:
                try:
                    try:
                        record = self.log_queue.get(timeout=0.1)
                        if record is None:
                            break
                        batch.append(record)
                    except Empty:
                        pass
                    current_time = time.time()
                    should_flush = (
                        len(batch) >= self.batch_size or
                        (batch and current_time - last_flush_time >= self.flush_interval)
                    )
                    if should_flush and batch:
                        self._write_batch(batch)
                        batch.clear()
                        last_flush_time = current_time
                except Exception:
                    pass
            if batch:
                self._write_batch(batch)
        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def _write_batch(self, batch):
        try:
            for record in batch:
                self.target_handler.emit(record)
            if hasattr(self.target_handler, 'flush'):
                self.target_handler.flush()
            self.stats['batches_written'] += 1
        except Exception:
            pass

    def emit(self, record):
        try:
            self.log_queue.put_nowait(record)
            self.stats['total_logs'] += 1
        except Exception:
            self.stats['queue_full_drops'] += 1

    def get_stats(self):
        return {**self.stats, 'queue_size': self.log_queue.qsize(), 'is_running': self.running}

    def close(self):
        self.running = False
        self.log_queue.put(None)
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        super().close()


def setup_high_performance_logging(program_name, log_dir=None, use_async=False):
    logging.setLoggerClass(ProgramLogger)
    if log_dir is None:
        log_dir = os.path.dirname(os.path.abspath(__file__))

    date_format = "%Y-%m-%d %H:%M:%S"
    format_str = "%(asctime)s - [PID:%(process)d] [%(trace_id)s] [%(task_id)s] - %(levelname)s - %(message)s"
    formatter = logging.Formatter(format_str, date_format)

    trace_id_filter = TraceIDFilter()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(trace_id_filter)

    LOG_FILE = os.path.join(log_dir, f"{program_name}_{os.getpid()}.log")

    if use_async:
        base_file_handler = logging.handlers.TimedRotatingFileHandler(
            LOG_FILE, when='midnight', interval=1, backupCount=10, encoding='utf-8', delay=False
        )
        base_file_handler.setFormatter(formatter)
        base_file_handler.addFilter(trace_id_filter)
        file_handler = AsyncBatchLogHandler(base_file_handler, batch_size=50000, flush_interval=5.0, max_queue_size=10000)
    else:
        file_handler = logging.handlers.TimedRotatingFileHandler(
            LOG_FILE, when='midnight', interval=1, backupCount=10, encoding='utf-8', delay=False
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(trace_id_filter)

    logger = logging.getLogger(program_name)
    if not isinstance(logger, ProgramLogger):
        logging.Logger.manager.loggerDict.pop(program_name, None)
        logger = logging.getLogger(program_name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False
    logger.program_name = program_name

    return logger, trace_id_filter, file_handler
