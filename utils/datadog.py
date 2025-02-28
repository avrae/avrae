import json
import logging
import sys

import ddtrace
import ddtrace.sampler
from ddtrace.profiling import Profiler

from utils import config


class JSONFormatter(logging.Formatter):
    """Custom formatter to log messages in JSON format for Datadog"""

    def format(self, record):
        log_record = {
            "log": record.getMessage(),
            "level": record.levelname,
            "dd.env": f"{config.ENVIRONMENT}",
            "dd.version": "1.0",
        }
        # Add error fields if it's an error log
        if record.levelno >= logging.ERROR:
            log_record["error.kind"] = type(record).__name__ if record else None
            log_record["error.message"] = str(record.exc_info[1]) if record.exc_info else None
            log_record["error.stack"] = self.formatException(record.exc_info) if record.exc_info else None

        return json.dumps(log_record)


def do_patches():
    ddtrace.config.env = config.ENVIRONMENT
    ddtrace.config.service = config.DD_SERVICE
    ddtrace.config.version = config.GIT_COMMIT_SHA
    ddtrace.tracer.configure(
        sampler=ddtrace.sampler.DatadogSampler(rules=[ddtrace.sampler.SamplingRule(sample_rate=0.90)])
    )
    ddtrace.patch_all(logging=True)
    _patch_logging()
    _patch_discord()
    _patch_aliasing()


def start_profiler():
    profiler = Profiler(
        env=config.ENVIRONMENT,
        service=config.DD_SERVICE,
        version=config.GIT_COMMIT_SHA,
    )
    profiler.start()


# ==== monkey-patches ====
def _patch_logging():
    logging.basicConfig(
        format=(
            "%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] "
            "[dd.service=%(dd.service)s dd.env=%(dd.env)s "
            "dd.version=%(dd.version)s "
            "dd.trace_id=%(dd.trace_id)s dd.span_id=%(dd.span_id)s]"
            "- %(message)s"
        ),
        level=logging.INFO,
        stream=sys.stdout,
    )


def _patch_discord():
    import disnake.ext.commands

    async def _command_invoke(self, *args, **kwargs):
        with ddtrace.tracer.trace(f"command: {self.qualified_name}"):
            await self._invoke(*args, **kwargs)

    disnake.ext.commands.Command._invoke = disnake.ext.commands.Command.invoke
    disnake.ext.commands.Command.invoke = _command_invoke


def _patch_aliasing():
    import aliasing.helpers

    real_handle_aliases = aliasing.helpers.handle_aliases

    async def _handle_aliases(*args, **kwargs):
        with ddtrace.tracer.trace("handle_aliases"):
            await real_handle_aliases(*args, **kwargs)

    aliasing.helpers.handle_aliases = _handle_aliases


datadog_logger = logging.getLogger("datadog")
datadog_logger.setLevel(logging.INFO)
datadog_logger.propagate = False

json_handler = logging.StreamHandler(sys.stdout)
json_handler.setFormatter(JSONFormatter())

datadog_logger.addHandler(json_handler)
