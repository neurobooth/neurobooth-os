Contributions
-------------

Contributions are welcome in the form of feedback and discussion in issues,
or pull requests for changes to the code.

Once the implementation of a piece of functionality is considered to be bug
free and properly documented (both API docs and an example script),
it can be incorporated into the `main` branch.

To help developing `neurobooth_os`, you will need to install as shown below.

Before submitting a pull request, we recommend that you run all style checks
and the test suite, and build the documentation **locally** on your machine.
That way, you can fix errors with your changes before submitting something
for review.

Setting up a development environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To start with, you should install `neurobooth_os` as described in our
[installation documentation](https://neurobooth.github.io).
For a development environment we recommend that you perform the installation in
a dedicated Python environment, for example using `conda`.
Afterwards, a few additional steps need to be performed.
For all of the steps below we assume that you work in your dedicated `neurobooth`
Python environment.

Install the development version of neurobooth_os
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Now [fork](https://help.github.com/en/github/getting-started-with-github/fork-a-repo) the `neurobooth_os` repository.
Then, `git clone` your fork and install it in "editable" mode.

```Shell
git clone https://github.com/<your-GitHub-username>/neurobooth-os
pip install -e ./neurobooth-os
```

You should now have the `neurobooth` development versions available in your Python environment.

### Install additional Python packages required for development

Navigate to the root of the `neurobooth_os` repository and call:

```Shell
pip install -r requirements_dev.txt
```

This will install several packages to run tests, and build the documentation
for `neurobooth_os`.

Install GNU Make
~~~~~~~~~~~~~~~~

We use [GNU Make](https://www.gnu.org/software/make/) for developing `neurobooth`.
We recommend that you install GNU Make and make use of our `Makefile` at the root
of the repository.
For most Linux and OSX operating systems, GNU Make will be already installed by default.
Windows users can download the [Chocolatey package manager](https://chocolatey.org/)
and install [GNU Make from their repository](https://community.chocolatey.org/packages/make).

If for some reason you can't install GNU Make, it might suffice to inspect
the `Makefile` and to figure out how to run the commands without invoking `make`.

Making style checks
~~~~~~~~~~~~~~~~~~~

We run several style checks on `neurobooth_os`.
If you have accurately followed the steps to setup your `neurobooth_os`
development version, you can simply call from the root of the
`neurobooth_os` repository:

```Shell
make pep
```

Running tests
~~~~~~~~~~~~~

We run tests using `pytest`.
If you have accurately followed the steps to setup your `neurobooth_os`
development version, you can simply call from the root of the
`neurobooth_os` repository:

```Shell
make test
```

Building the documentation
~~~~~~~~~~~~~~~~~~~~~~~~~~

The documentation can be built using [Sphinx](https://www.sphinx-doc.org).
If you have accurately followed the steps to setup your `neurobooth_os` development version,
you can simply call from the root of the `neurobooth_os` repository:

```Shell
make build-doc
```

or, if you don't want to run the examples to build the documentation:

```Shell
make -C doc/ html-noplot
```

The latter command will result in a faster build but produce no plots in the examples.
