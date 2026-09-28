import time
import os

try:
    from toxictools import fast_upload, fast_download, progress_bar_str, human_readable_size, Timer
except ImportError:
    from toxic.core.fast_pyro import fast_upload, fast_download

    def human_readable_size(size):
        if not size:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"

    def progress_bar_str(current, total):
        if not total:
            return "[□□□□□□□□□□] 0.00%"
        percentage = current * 100 / total
        completed = min(10, max(0, int(percentage / 10)))
        return f"[{'■' * completed}{'□' * (10 - completed)}] {percentage:.2f}%"

    class Timer:
        def __init__(self, time_between=5):
            self.start_time = time.time()
            self.time_between = time_between
            self.last_time = time.time()

        def can_send(self):
            if time.time() - self.last_time > self.time_between:
                self.last_time = time.time()
                return True
            return False
