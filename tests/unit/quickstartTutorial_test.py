import pytest
import aiohttp
import d20
import asyncio
import functools
from unittest.mock import Mock, AsyncMock, patch
from cogsmisc.tutorials.quickstart import Quickstart


def async_function_wrapper(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if asyncio.iscoroutinefunction(func):
            return func(*args, **kwargs)
        else:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(func(*args, **kwargs))
            finally:
                loop.close()
                asyncio.set_event_loop(None)

    return wrapper


@pytest.fixture
def ctx_mock():
    ctx = Mock()
    ctx.prefix = "!"
    ctx.bot.get_command.return_value = Mock()
    return ctx


@pytest.fixture
def state_map_mock():
    return Mock()


@pytest.fixture
def quickstart_tutorial():
    return Quickstart()


@pytest.fixture
@async_function_wrapper
async def async_client_session():
    async with aiohttp.ClientSession() as session:
        yield session


# --- Start State ---
pytestmark = pytest.mark.asyncio


async def test_quickstarttutorial_start(
    quickstart_tutorial, ctx_mock, state_map_mock, async_client_session
):
    start_state = quickstart_tutorial.Start()
    start_state.tutorial = quickstart_tutorial

    with patch.object(
        start_state, "objective", AsyncMock(return_value=asyncio.Future())
    ) as mock_objective, patch.object(
        start_state, "listener", AsyncMock(return_value=asyncio.Future())
    ) as mock_listener, patch.object(
        start_state, "transition", AsyncMock(return_value=asyncio.Future())
    ) as mock_transition:
        await start_state.objective(ctx_mock, state_map_mock)
        await start_state.listener(ctx_mock, state_map_mock)
        await start_state.transition(ctx_mock, state_map_mock)

        mock_objective.assert_called_once_with(ctx_mock, state_map_mock)
        mock_listener.assert_called_once_with(ctx_mock, state_map_mock)
        mock_transition.assert_called_once_with(ctx_mock, state_map_mock)


# --- ImportCharacter State ---
pytestmark = pytest.mark.asyncio


async def test_quickstarttutorial_import_character(
    quickstart_tutorial, ctx_mock, state_map_mock, async_client_session
):
    import_state = quickstart_tutorial.ImportCharacter()
    import_state.tutorial = quickstart_tutorial

    with patch.object(
        import_state, "objective", AsyncMock(return_value=asyncio.Future())
    ) as mock_objective, patch.object(
        import_state, "listener", AsyncMock(return_value=asyncio.Future())
    ) as mock_listener, patch.object(
        import_state, "transition", AsyncMock(return_value=asyncio.Future())
    ) as mock_transition:
        await import_state.objective(ctx_mock, state_map_mock)
        await import_state.listener(ctx_mock, state_map_mock)
        await import_state.transition(ctx_mock, state_map_mock)

        mock_objective.assert_called_once_with(ctx_mock, state_map_mock)
        mock_listener.assert_called_once_with(ctx_mock, state_map_mock)
        mock_transition.assert_called_once_with(ctx_mock, state_map_mock)


# --- ChecksAttacksSaves State ---
pytestmark = pytest.mark.asyncio


async def test_quickstarttutorial_checks_attacks_saves(
    quickstart_tutorial, ctx_mock, state_map_mock, async_client_session
):
    checks_state = quickstart_tutorial.ChecksAttacksSaves()
    checks_state.tutorial = quickstart_tutorial

    with patch.object(
        checks_state, "objective", AsyncMock(return_value=asyncio.Future())
    ) as mock_objective, patch.object(
        checks_state, "listener", AsyncMock(return_value=asyncio.Future())
    ) as mock_listener, patch.object(
        checks_state, "transition", AsyncMock(return_value=asyncio.Future())
    ) as mock_transition:
        await checks_state.objective(ctx_mock, state_map_mock)
        await checks_state.listener(ctx_mock, state_map_mock)
        await checks_state.transition(ctx_mock, state_map_mock)

        mock_objective.assert_called_once_with(ctx_mock, state_map_mock)
        mock_listener.assert_called_once_with(ctx_mock, state_map_mock)
        mock_transition.assert_called_once_with(ctx_mock, state_map_mock)


# --- Actions State ---
pytestmark = pytest.mark.asyncio


async def test_quickstarttutorial_actions(
    quickstart_tutorial, ctx_mock, state_map_mock, async_client_session
):
    actions_state = quickstart_tutorial.Actions()
    actions_state.tutorial = quickstart_tutorial
    print(f"Start state: {actions_state}")

    with patch.object(
        actions_state, "objective", AsyncMock(return_value=asyncio.Future())
    ) as mock_objective, patch.object(
        actions_state, "listener", AsyncMock(return_value=asyncio.Future())
    ) as mock_listener, patch.object(
        actions_state, "transition", AsyncMock(return_value=asyncio.Future())
    ) as mock_transition:
        await actions_state.objective(ctx_mock, state_map_mock)
        await actions_state.listener(ctx_mock, state_map_mock)
        await actions_state.transition(ctx_mock, state_map_mock)

        mock_objective.assert_called_once_with(ctx_mock, state_map_mock)
        mock_listener.assert_called_once_with(ctx_mock, state_map_mock)
        mock_transition.assert_called_once_with(ctx_mock, state_map_mock)


def test_roll():
    assert type(d20.roll("1d20")) == d20.RollResult
    assert 0 < d20.roll("1d20").total < 21
    assert d20.roll("3+4*(9-2)").total == 31
