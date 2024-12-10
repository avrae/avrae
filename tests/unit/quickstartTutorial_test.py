import pytest
import aiohttp
import d20
import asyncio
import inspect
from unittest.mock import Mock, AsyncMock, patch
from cogsmisc.tutorials.quickstart import Quickstart
from cogsmisc.tutorials.models import TutorialState

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
async def async_client_session():
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture
def mock_redis_connection():
    with patch("redis.Redis", return_value=Mock()):
        yield


# Mark all tests in the module as asyncio-based
pytestmark = pytest.mark.asyncio


async def test_quickstarttutorial_start(
    quickstart_tutorial, ctx_mock, state_map_mock, async_client_session, mock_redis_connection
):
    start_state = quickstart_tutorial.Start
    start_state.tutorial = quickstart_tutorial

    for method_name in ["objective", "listener", "transition"]:
        method = getattr(start_state, method_name, None)
        assert inspect.getmodule(method) is not inspect.getmodule(TutorialState), (
            f"Method '{method_name}' must be overridden in {start_state.__class__.__name__}"
        )

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


async def test_quickstarttutorial_import_character(
    quickstart_tutorial, ctx_mock, state_map_mock, async_client_session, mock_redis_connection
):
    import_state = quickstart_tutorial.ImportCharacter
    import_state.tutorial = quickstart_tutorial

    for method_name in ["objective", "listener", "transition"]:
        method = getattr(import_state, method_name, None)
        assert inspect.getmodule(method) is not inspect.getmodule(TutorialState), (
            f"Method '{method_name}' must be overridden in {import_state.__class__.__name__}"
        )

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


async def test_quickstarttutorial_checks_attacks_saves(
    quickstart_tutorial, ctx_mock, state_map_mock, async_client_session, mock_redis_connection
):
    checks_state = quickstart_tutorial.ChecksAttacksSaves
    checks_state.tutorial = quickstart_tutorial

    for method_name in ["objective", "listener", "transition"]:
        method = getattr(checks_state, method_name, None)
        assert inspect.getmodule(method) is not inspect.getmodule(TutorialState), (
            f"Method '{method_name}' must be overridden in {checks_state.__class__.__name__}"
        )

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


async def test_quickstarttutorial_actions(
    quickstart_tutorial, ctx_mock, state_map_mock, async_client_session, mock_redis_connection
):
    actions_state = quickstart_tutorial.Actions
    actions_state.tutorial = quickstart_tutorial

    for method_name in ["objective", "listener", "transition"]:
        method = getattr(actions_state, method_name, None)
        assert inspect.getmodule(method) is not inspect.getmodule(TutorialState), (
            f"Method '{method_name}' must be overridden in {actions_state.__class__.__name__}"
        )

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
    roll_result = d20.roll("1d20")
    assert isinstance(roll_result, d20.RollResult)
    assert 0 < roll_result.total < 21
    assert d20.roll("3+4*(9-2)").total == 31
