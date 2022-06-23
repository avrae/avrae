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

TODO

## Writing Tests

### Unit Tests

### E2E Tests

### Gamedata Tests

### Fixtures

TODO
