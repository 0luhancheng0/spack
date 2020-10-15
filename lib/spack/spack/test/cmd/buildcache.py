# Copyright 2013-2020 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import errno
import platform
import os

import pytest

import spack.main
import spack.binary_distribution
import spack.environment as ev
import spack.spec
from spack.spec import Spec

buildcache = spack.main.SpackCommand('buildcache')
install = spack.main.SpackCommand('install')
uninstall = spack.main.SpackCommand('uninstall')
spec = spack.main.SpackCommand('spec')
env = spack.main.SpackCommand('env')
add = spack.main.SpackCommand('add')


@pytest.fixture()
def mock_get_specs(database, monkeypatch):
    specs = database.query_local()
    monkeypatch.setattr(
        spack.binary_distribution, 'get_specs', lambda: specs
    )


@pytest.fixture()
def mock_get_specs_multiarch(database, monkeypatch):
    specs = [spec.copy() for spec in database.query_local()]

    # make one spec that is NOT the test architecture
    for spec in specs:
        if spec.name == "mpileaks":
            spec.architecture = spack.spec.ArchSpec('linux-rhel7-x86_64')
            break

    monkeypatch.setattr(
        spack.binary_distribution, 'get_specs', lambda: specs
    )


@pytest.mark.skipif(
    platform.system().lower() != 'linux',
    reason='implementation for MacOS still missing'
)
@pytest.mark.db
def test_buildcache_preview_just_runs(database):
    buildcache('preview', 'mpileaks')


@pytest.mark.db
@pytest.mark.regression('13757')
def test_buildcache_list_duplicates(mock_get_specs, mutable_database, capsys):
    with capsys.disabled():
        output = buildcache('list', 'mpileaks', '@2.3')

    assert output.count('mpileaks') == 3


@pytest.mark.db
@pytest.mark.regression('17827')
def test_buildcache_list_allarch(
        mutable_database, mock_get_specs_multiarch, capsys):
    with capsys.disabled():
        output = buildcache('list', '--allarch')

    assert output.count('mpileaks') == 3

    with capsys.disabled():
        output = buildcache('list')

    assert output.count('mpileaks') == 2


@pytest.mark.db
@pytest.mark.regression('reference listed binaries by hash')
def test_buildcache_reference_by_hash(
        mutable_database, mock_get_specs, capsys):
    expected = mutable_database.query(installed=True)
    uninstall('-a', '-y')

    assert not mutable_database.query()
    buildcache('list')

    found = mutable_database.query(installed=any)
    found_installed = mutable_database.query(installed=True)

    assert found == expected
    assert found_installed == [s for s in expected if s.external]
    assert len(found_installed) < len(found)

    uninstalled = list(set(found) - set(found_installed))
    spec('/%s' % uninstalled[0].dag_hash())  # failure raises


def tests_buildcache_create(
        install_mockery, mock_fetch, monkeypatch, tmpdir):
    """"Ensure that buildcache create creates output files"""
    pkg = 'trivial-install-test-package'
    install(pkg)

    buildcache('create', '-d', str(tmpdir), '--unsigned', pkg)

    spec = Spec(pkg).concretized()
    tarball_path = spack.binary_distribution.tarball_path_name(spec, '.spack')
    tarball = spack.binary_distribution.tarball_name(spec, '.spec.yaml')
    assert os.path.exists(
        os.path.join(str(tmpdir), 'build_cache', tarball_path))
    assert os.path.exists(
        os.path.join(str(tmpdir), 'build_cache', tarball))


def tests_buildcache_create_env(
        install_mockery, mock_fetch, monkeypatch,
        tmpdir, mutable_mock_env_path):
    """"Ensure that buildcache create creates output files from env"""
    pkg = 'trivial-install-test-package'

    env('create', 'test')
    with ev.read('test'):
        add(pkg)
        install()

        buildcache('create', '-d', str(tmpdir), '--unsigned')

    spec = Spec(pkg).concretized()
    tarball_path = spack.binary_distribution.tarball_path_name(spec, '.spack')
    tarball = spack.binary_distribution.tarball_name(spec, '.spec.yaml')
    assert os.path.exists(
        os.path.join(str(tmpdir), 'build_cache', tarball_path))
    assert os.path.exists(
        os.path.join(str(tmpdir), 'build_cache', tarball))


def test_buildcache_create_fails_on_noargs(tmpdir):
    """Ensure that buildcache create fails when given no args or
    environment."""
    with pytest.raises(spack.main.SpackCommandError):
        buildcache('create', '-d', str(tmpdir), '--unsigned')


def test_buildcache_create_fail_on_perm_denied(
        install_mockery, mock_fetch, monkeypatch, tmpdir):
    """Ensure that buildcache create fails on permission denied error."""
    install('trivial-install-test-package')

    tmpdir.chmod(0)
    with pytest.raises(OSError) as error:
        buildcache('create', '-d', str(tmpdir),
                   '--unsigned', 'trivial-install-test-package')
    assert error.value.errno == errno.EACCES
    tmpdir.chmod(0o700)
