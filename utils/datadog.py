import ddtrace
from ddtrace.profiling import Profiler

from utils import config


def do_patches():
    ddtrace.config.env = config.ENVIRONMENT
    ddtrace.config.service = config.DD_SERVICE
    ddtrace.config.version = config.GIT_COMMIT_SHA
    ddtrace.patch_all(
        aiohttp=True
    )


def start_profiler():
    prof = Profiler(
        env=config.ENVIRONMENT,
        service=config.DD_SERVICE,
        version=config.GIT_COMMIT_SHA,
    )
    prof.start()
