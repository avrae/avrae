# Avrae Tests

The Avrae test suite is comprised of three primary parts: end-to-end (E2E) testing (`e2e/`), unit testing (`unit/`), and
gamedata simulation testing (`gamedata/`).

## Setup

```shell
(venv) $ pip install -r tests/requirements.txt
```

The test environment requires MongoDB and Redis to be set up to facilitate the E2E tests. You can either use Docker
and the `docker-compose.ci.yml` Compose file, or set up these services and the following environment variables yourself:

### Required Environment Variables

- `NO_DICECLOUD`: Set this to `1`. This disables the Dicecloud client which would otherwise try to connect on startup.
- `DISCORD_OWNER_USER_ID`: This can be any random number.
- `MONGO_URL`: A MongoDB connection url.
- `REDIS_URL`: A Redis connection url.

In order to run the gamedata simulation tests, you'll also need to set the following environment variables:

### Gamedata Environment Variables

- `TEST_GAMEDATA_BASE_PATH`: A path to the directory containing the canonical gamedata. Defaults
  to `tests/static/compendium`.
- `TEST_SIMULATION_BASE_PATH`: A path to the directory containing the simulation files under test (`actions.json`
  , `monsters.json`, `spells.json`). Defaults to `tests/static/compendium`.

## Running Tests

Once all the environment variables have been set, you can run the tests with:

```shell
(venv) $ pytest
```

If you have set the gamedata tests to point to real gamedata, this will run over 55,000 tests! To filter this, a number
of pytest marks are provided to allow filtering the tests:

- `e2e`
- `unit`
- `gamedata`
- `simulation`

Use the `-m` flag to select the marks to run. For example, to select only the non-gamedata tests, you could
use `pytest -m "not gamedata"`.

## Writing Tests

Pytest will automatically discover test files in the `tests/` directory, as long as the file is named in the pattern of
`*_test.py`. Inside each test file, a test is comprised of a function named `test_*()`. See the pytest docs for more
information.

### Unit Tests

Unit tests test a *unit* of code - usually one function or method - and run assertions on the outputs of that function
given its inputs. They're usually the right kind of test for parsing, utility functions, and self-contained units.

To add a new unit test, add it to the `tests/unit` directory, using the other unit test files as an example.

These are the preferred test type in general because they encourage good code encapsulation.

### E2E Tests

End-to-end tests test the entire *system*, as opposed to a single unit of code. Generally, these tests function by
sending a fake Discord message to Avrae, then watching what Avrae would send back to Discord and running assertions
on this output. E2E tests can also run assertions on state after Avrae finishes processing a message by using
helpers to retrieve character or combat state.

E2E tests depend on two primary fixtures:

- `avrae` is the instance of the bot, with a couple of utility methods monkey-patched in.
    - Use `avrae.message("!command")` to send mock Discord messages to Avrae during E2E tests.
- `dhttp` is the mock Discord HTTP client, which records the HTTP requests Avrae would have made to the Discord API.
    - Use `await dhttp.receive_*` to run assertions on the requests Avrae would make to Discord.
    - For example, `await dhttp.receive_message("Hello world")` would require Avrae to send a message with the
      content `Hello world`. `dhttp` methods contain arguments to help loosely match content - see `tests/mocks.py` and
      other E2E tests for examples.

`tests/utils.py` contains multiple helpers to assist writing E2E tests.

### Gamedata Tests

Gamedata tests run simulations on every official automation document in order to ensure that there are no errors in
the Automation Engine. Generally, these are added by writing more official automation, rather than gamedata tests.

As these tests operate on non-SRD data, care must be taken not to expose the underlying data in the tests. For PRs
opened by outside contributors, a project maintainer must approve the gamedata test workflow by adding the `ci: approve`
label to the PR. Maintainers may need to remove and re-add the label to rerun the PR after PR updates.

### Fixtures

#### E2E/Unit Fixtures

- `dhttp`: The mock Discord client, used to run assertions on bot output. See E2E Tests above.
- `avrae`: The Avrae instance, used to send mock messages. See E2E Tests above.
- `character`: A parameterized fixture that provides various Character objects and sets the yielded character as the
  active character in the test db.
- `init_fixture`: A fixture that should be used at the class scope to clean up after a group if initiative tests.

#### Gamedata/Simulation Fixtures

- `spells`: A fixture providing the entirety of `spells.json`.
- `monsters`: A fixture providing the entirety of `monsters.json`.
- `actions`: A fixture providing the entirety of `actions.json`.
- `spell`: A parameterized fixture providing each spell in `spells.json` individually.
- `monster`: A parameterized fixture providing each monster in `monsters.json` individually.
- `monster_attack`: A parameterized fixture providing each attack of each monster in `monsters.json` individually.
- `action`: A parameterized fixture providing each action in `actions.json` individually.
- `bob`: A generic StatBlock caster that includes spellcasting information.
- `ara`: A Character caster (level 10 Bard/Warlock). Does not set up the DB (c.f. `character`).
- `mock_combat`: A fixture that provides an ephemeral Combat instance for use in simulation tests without having to
  start a combat using E2E methods.
