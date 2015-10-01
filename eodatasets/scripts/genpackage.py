#!/usr/bin/env python
# coding=utf-8
from __future__ import absolute_import
import os
import tempfile

import click
from pathlib import Path

from eodatasets import package, drivers, serialise
from eodatasets.scripts import init_logging


@click.command()
@click.option('--parent',
              type=click.Path(exists=True, readable=True, writable=False),
              multiple=True,
              help='Path of the parent dataset (that these datasets were derived from.)')
@click.option('--debug',
              is_flag=True,
              help='Enable debug logging')
@click.option('--hard-link',
              is_flag=True,
              help='Hard-link output files if possible (faster than copying)')
@click.argument('package_type',
                type=click.Choice(drivers.PACKAGE_DRIVERS.keys()))
@click.argument('dataset',
                type=click.Path(exists=True, readable=True, writable=False),
                nargs=-1)
@click.argument('destination',
                type=click.Path(exists=True, readable=True, writable=True),
                nargs=1)
def run(parent, debug, hard_link, package_type, dataset, destination):
    """
    Package the given imagery folders.
    """
    init_logging(debug)

    parent_datasets = {}

    #: :type: package.DatasetDriver
    driver = drivers.PACKAGE_DRIVERS[package_type]

    # TODO: Multiple parents?
    if parent:
        source_id = driver.expected_source().get_id()
        parent_datasets.update({source_id: serialise.read_dataset_metadata(Path(parent[0]))})

    for dataset_folder in dataset:
        dataset_path = Path(dataset_folder)
        temp_output_dir = Path(tempfile.mkdtemp(prefix='.packagetmp.', dir=destination))

        new_dataset = package.package_dataset(
            package.init_existing_dataset(dataset_path, driver, parent_datasets),
            dataset_path,
            temp_output_dir,
            hard_link=hard_link
        )

        os.rename(str(temp_output_dir), os.path.join(destination, new_dataset.ga_label))


if __name__ == '__main__':
    # Click fills out the parameters, which confuses pylint.
    # pylint: disable=no-value-for-parameter
    run()
