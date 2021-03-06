"""Development automation
"""

import nox

nox.options.sessions = ["lint", "test"]
nox.options.reuse_existing_virtualenvs = True


@nox.session(python="3.8")
def lint(session):
    session.install("pre-commit")

    if session.posargs:
        args = session.posargs + ["--all-files"]
    else:
        args = ["--all-files", "--show-diff-on-failure"]

    session.run("pre-commit", "run", "--all-files", *args)


@nox.session(python=["2.7", "3.5", "3.6", "3.7", "3.8", "pypy2", "pypy3"])
def test(session):
    session.install(".[test]")

    session.run(
        "pytest",
        "--cov=installer",
        "--cov-fail-under=100",
        "-n",
        "auto",
        *session.posargs
    )
