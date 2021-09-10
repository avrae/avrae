import logging
import traceback


class DetailedErrorHandler(logging.StreamHandler):
    """
    Event handler that prints out stack info for each error-level log
    Mainly used for debugging mysterious error logs from transitive dependencies
    You probably shouldn't use this in prod but who am I to stop you
    """

    def emit(self, record):
        super().emit(record)
        if record.levelname != 'ERROR':
            return
        print(record.pathname, record.lineno)
        traceback.print_stack()
