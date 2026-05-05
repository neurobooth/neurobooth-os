Contributions
-------------

Contributions are welcome in the form of feedback and discussion in issues,
or pull requests for changes to the code.

Once the implementation of a piece of functionality is considered to be bug
free and properly documented (both API docs and an example script),
it can be incorporated into the `main` branch.

To help developing `neurobooth_os`, you will need to install as shown below.

Before submitting a pull request, we recommend that you run all style checks
and the test suite **locally** on your machine. That way, you can fix errors
with your changes before submitting something for review.

Setting up a development environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The project uses `uv <https://docs.astral.sh/uv/>`_ for dependency
management; see the README for installation. Once uv is on PATH:

```Shell
git clone https://github.com/<your-GitHub-username>/neurobooth-os
cd neurobooth-os
uv sync --group dev
```

`uv sync` creates a `.venv` with the locked runtime dependencies, and the
`--group dev` flag adds the developer toolchain (pytest, ruff, mypy,
sphinx). The project itself is installed editable; code changes show up
immediately.

You should now have the `neurobooth` development version available in
your Python environment. Run anything from the venv with `uv run ...`,
or activate it explicitly:

```Shell
.venv\Scripts\activate.bat
```

Style checks
~~~~~~~~~~~~

We use `ruff` for linting and formatting (installed by ``uv sync --group dev``).
From the repo root:

```Shell
uv run ruff check
uv run ruff format --check
```

Running tests
~~~~~~~~~~~~~

We use `pytest` (installed by ``uv sync --group dev``). From the repo root:

```Shell
uv run pytest
```

Some tests pull in `pylink` via the `tasks` package; they need the
`eyelink` extra to be installed:

```Shell
uv sync --extra eyelink
```

Type checks
~~~~~~~~~~~

`pyproject.toml` configures strict mypy settings. From the repo root:

```Shell
uv run mypy neurobooth_os
```
