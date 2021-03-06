__authors__ = ["Tobias Marschall", "Marcel Martin", "Johannes Köster"]
__copyright__ = "Copyright 2015-2019, Johannes Köster"
__email__ = "johannes.koester@uni-due.de"
__license__ = "MIT"

import sys
import os
import shutil
from os.path import join
from subprocess import call
import tempfile
import hashlib
import urllib
from shutil import rmtree, which
from shlex import quote
import pytest
import subprocess

from snakemake import snakemake
from snakemake.shell import shell


def dpath(path):
    """get path to a data file (relative to the directory this
	test lives in)"""
    return os.path.realpath(join(os.path.dirname(__file__), path))


def md5sum(filename):
    data = open(filename, "rb").read()
    return hashlib.md5(data).hexdigest()


# test skipping
def is_connected():
    try:
        urllib.request.urlopen("http://www.google.com", timeout=1)
        return True
    except urllib.request.URLError:
        return False


def is_ci():
    return "CI" in os.environ


def has_gcloud_service_key():
    return "GCP_AVAILABLE" in os.environ


gcloud = pytest.mark.skipif(
    not is_connected() or not has_gcloud_service_key(),
    reason="Skipping GCLOUD tests because not on "
    "CI, no inet connection or not logged "
    "in to gcloud.",
)

connected = pytest.mark.skipif(not is_connected(), reason="no internet connection")

ci = pytest.mark.skipif(not is_ci(), reason="not in CI")
not_ci = pytest.mark.skipif(is_ci(), reason="skipped in CI")


def copy(src, dst):
    if os.path.isdir(src):
        shutil.copytree(src, os.path.join(dst, os.path.basename(src)))
    else:
        shutil.copy(src, dst)


def run(
    path,
    shouldfail=False,
    snakefile="Snakefile",
    subpath=None,
    no_tmpdir=False,
    check_md5=True,
    cores=3,
    set_pythonpath=True,
    cleanup=True,
    conda_frontend="mamba",
    **params
):
    """
    Test the Snakefile in path.
    There must be a Snakefile in the path and a subdirectory named
    expected-results. If cleanup is False, we return the temporary
    directory to the calling test for inspection, and the test should
    clean it up.
    """
    if set_pythonpath:
        # Enforce current workdir (the snakemake source dir) to also be in PYTHONPATH
        # when subprocesses are invoked in the tempdir defined below.
        os.environ["PYTHONPATH"] = os.getcwd()
    elif "PYTHONPATH" in os.environ:
        del os.environ["PYTHONPATH"]

    results_dir = join(path, "expected-results")
    snakefile = join(path, snakefile)
    assert os.path.exists(snakefile)
    assert os.path.exists(results_dir) and os.path.isdir(
        results_dir
    ), "{} does not exist".format(results_dir)

    # If we need to further check results, we won't cleanup tmpdir
    tmpdir = next(tempfile._get_candidate_names())
    tmpdir = os.path.join(tempfile.gettempdir(), "snakemake-%s" % tmpdir)
    os.mkdir(tmpdir)

    config = {}

    # handle subworkflow
    if subpath is not None:
        # set up a working directory for the subworkflow and pass it in `config`
        # for now, only one subworkflow is supported
        assert os.path.exists(subpath) and os.path.isdir(
            subpath
        ), "{} does not exist".format(subpath)
        subworkdir = os.path.join(tmpdir, "subworkdir")
        os.mkdir(subworkdir)

        # copy files
        for f in os.listdir(subpath):
            copy(os.path.join(subpath, f), subworkdir)
        config["subworkdir"] = subworkdir

    # copy files
    for f in os.listdir(path):
        print(f)
        copy(os.path.join(path, f), tmpdir)

    # run snakemake
    success = snakemake(
        snakefile,
        cores=cores,
        workdir=path if no_tmpdir else tmpdir,
        stats="stats.txt",
        config=config,
        verbose=True,
        conda_frontend=conda_frontend,
        **params
    )
    if shouldfail:
        assert not success, "expected error on execution"
    else:
        assert success, "expected successful execution"
        for resultfile in os.listdir(results_dir):
            if resultfile in [".gitignore", ".gitkeep"] or not os.path.isfile(
                os.path.join(results_dir, resultfile)
            ):
                # this means tests cannot use directories as output files
                continue
            targetfile = join(tmpdir, resultfile)
            expectedfile = join(results_dir, resultfile)
            assert os.path.exists(targetfile), 'expected file "{}" not produced'.format(
                resultfile
            )
            if check_md5:
                # if md5sum(targetfile) != md5sum(expectedfile):
                #     import pdb; pdb.set_trace()
                if md5sum(targetfile) != md5sum(expectedfile):
                    with open(targetfile) as target:
                        content = target.read()
                    assert False, 'wrong result produced for file "{}":\n{}'.format(
                        resultfile, content
                    )

    if not cleanup:
        return tmpdir
    shutil.rmtree(tmpdir)
