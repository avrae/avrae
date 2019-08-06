import asyncio
import os

import motor.motor_asyncio
import newrelic.agent
from discord.ext import commands
from newrelic.api.function_trace import wrap_function_trace
from newrelic.api.transaction import current_transaction

application = newrelic.agent.application()

_motor_classes = {
    'AsyncIOMotorCollection': [
        'count_documents',
        'delete_many',
        'delete_one',
        'find',
        'find_one',
        'insert_one',
        'update_many',
        'update_one',
    ],
    'AsyncIOMotorCursor': [
        'to_list',
    ],
}


def hook_all():
    if os.getenv('NEW_RELIC_LICENSE_KEY') is None:
        return

    hook_discord()
    hook_motor()


def hook_discord():
    # The normal New Relic API doesn't work here, let's replace the existing `Command.invoke` function with a version
    # that wraps it in a background task transaction
    async def _command_invoke(self, *args, **kwargs):
        # If there's already a running transaction, don't start a new one. New Relic doesn't handle coroutines very
        # well.
        transaction = current_transaction()
        if transaction:
            return await self._invoke(*args, **kwargs)

        with newrelic.agent.BackgroundTask(application, name='command: %s' % self.qualified_name):
            await self._invoke(*args, **kwargs)

    commands.Command._invoke = commands.Command.invoke
    commands.Command.invoke = _command_invoke

    # We can just hook these the simple way
    wrap_function_trace(asyncio, 'wait_for', name='asyncio: wait_for')


def hook_motor():
    for class_name, methods in _motor_classes.items():
        thing = getattr(motor.motor_asyncio, class_name)
        if thing is not None:
            for method in methods:
                if hasattr(thing, method):
                    wrap_function_trace(
                        motor.motor_asyncio,
                        '%s.%s' % (class_name, method),
                        name='motor: %s.%s' % (class_name, method))
