# coding=utf-8
from __future__ import absolute_import
import os
import shutil
import logging
from subprocess import check_call
import datetime
import uuid
import socket
import copy

from pathlib import Path

from eodatasets import serialise, verify, metadata
from eodatasets.browseimage import create_dataset_browse_images
import eodatasets.type as ptype


GA_CHECKSUMS_FILE_NAME = 'package.sha1'

_LOG = logging.getLogger(__name__)

_RUNTIME_ID = uuid.uuid1()


def init_locally_processed_dataset(directory, dataset_driver, source_datasets,
                                   software_provenance, uuid_=None):
    """
    Create a blank dataset for a newly created dataset on this machine.

    :type software_provenance: eodatasets.provenance.SoftwareProvenance
    :param uuid_: The existing dataset_id, if any.
    :rtype: ptype.DatasetMetadata
    """
    md = ptype.DatasetMetadata(
        id_=uuid_,
        # Default creation time is creation of an image.
        creation_dt=datetime.datetime.utcfromtimestamp(directory.stat().st_ctime),
        lineage=ptype.LineageMetadata(
            machine=ptype.MachineMetadata(
                hostname=socket.getfqdn(),
                runtime_id=_RUNTIME_ID,
                software=software_provenance,
                uname=' '.join(os.uname())
            ),
            source_datasets=source_datasets
        )
    )
    return dataset_driver.fill_metadata(md, directory)


def init_existing_dataset(directory, dataset_driver, source_datasets,
                          software_provenance=None, uuid_=None, source_hostname=None):
    """
    Package an existing dataset folder (with mostly unknown provenance).

    This is intended for old datasets where little information was recorded.

    For brand new datasets, it's better to use init_locally_processed_dataset() to capture
    local machine information.

    :param uuid_: The existing dataset_id, if any.
    :param source_hostname: Hostname where processed, if known.
    :rtype: ptype.DatasetMetadata
    """
    md = ptype.DatasetMetadata(
        id_=uuid_,
        # Default creation time is creation of an image.
        creation_dt=datetime.datetime.utcfromtimestamp(directory.stat().st_ctime),
        lineage=ptype.LineageMetadata(
            machine=ptype.MachineMetadata(
                hostname=source_hostname,
                software=software_provenance
            ),
            source_datasets=source_datasets

        )
    )
    return dataset_driver.fill_metadata(md, directory)


def _copy_file(source_path, destination_path, compress_imagery=True, hard_link=False):
    """
    Copy a file from source to destination if needed. Maybe apply compression.

    (it's generally faster to compress during a copy operation than as a separate step)

    :type source_path: Path
    :type destination_path: Path
    :type compress_imagery: bool
    :type hard_link: bool
    :return: Size in bytes of destination file.
    :rtype int
    """

    source_file = str(source_path)
    destination_file = str(destination_path)

    # Copy to destination path.
    original_suffix = source_path.suffix.lower()
    suffix = destination_path.suffix.lower()

    if destination_path.exists():
        _LOG.info('Destination exists: %r', destination_file)
    elif (original_suffix == suffix) and hard_link:
        _LOG.info('Hard linking %r -> %r', source_file, destination_file)
        os.link(source_file, destination_file)
    # If a tif image, compress it losslessly.
    elif suffix == '.tif' and compress_imagery:
        _LOG.info('Copying compressed %r -> %r', source_file, destination_file)
        check_call(
            [
                'gdal_translate',
                '--config', 'GDAL_CACHEMAX', '512',
                '--config', 'TILED', 'YES',
                '-co', 'COMPRESS=lzw',
                source_file, destination_file
            ]
        )
    else:
        _LOG.info('Copying %r -> %r', source_file, destination_file)
        shutil.copy(source_file, destination_file)

    return destination_path.stat().st_size


class IncompletePackage(Exception):
    """
    Package is incomplete: (eg. Not enough metadata could be found.)
    """
    pass


def _folder_contents_bytes(image_path):
    return _file_size_bytes(image_path.iterdir())


def _file_size_bytes(*file_paths):
    """
    Total file size for the given paths.
    :type file_paths: list[Path]
    :rtype: int
    """
    return sum([p.stat().st_size for p in file_paths])


def validate_metadata(dataset):
    """
    :rtype: ptype.DatasetMetadata
    """
    # TODO: Add proper validation
    if not dataset.platform or not dataset.platform.code:
        raise IncompletePackage('Incomplete dataset. Not enough metadata found: %r' % dataset)


def package_inplace_dataset(dataset, path):
    """
    Create a metadata file for the given dataset without modifying it.

    :type dataset: ptype.Dataset
    :type path: Path
    :rtype: Path
    :return: Path to the created metadata file.
    """
    typical_checksum_file = path.joinpath(GA_CHECKSUMS_FILE_NAME)
    if typical_checksum_file.exists():
        dataset.checksum_path = typical_checksum_file

    validate_metadata(dataset)
    dataset = metadata.expand_common_metadata(dataset)
    return serialise.write_dataset_metadata(path, dataset)


def package_dataset(dataset,
                    image_path,
                    target_path,
                    hard_link=False):
    """
    Package the given dataset folder.

    This includes copying the dataset into a folder, generating
    metadata and checksum files, as well as optionally generating
    a browse image.

    :type hard_link: bool
    :type dataset_driver: eodatasets.drivers.DatasetDriver
    :type dataset: ptype.Dataset
    :type image_path: Path
    :type target_path: Path

    :raises IncompletePackage: If not enough metadata can be extracted from the dataset.
    :return: The generated GA Dataset ID (ga_label)
    :rtype: str
    """
    checksums = verify.PackageChecksum()

    target_path = target_path.absolute()
    image_path = image_path.absolute()

    target_metadata_path = serialise.expected_metadata_path(target_path)
    if target_metadata_path.exists():
        _LOG.info('Already packaged? Skipping %s', target_path)
        return

    _LOG.debug('Packaging %r -> %r', image_path, target_path)
    package_directory = target_path.joinpath('product')
    if not package_directory.exists():
        package_directory.mkdir()

    def after_file_copy(source_path, target_path):
        _LOG.debug('%r -> %r', source_path, target_path)
        checksums.add_file(target_path)

    #: :type: ptype.DatasetMetadata
    dataset = copy.deepcopy(dataset)

    if dataset.image and dataset.image.bands:
        for _, band in dataset.image.bands.iteritems():
            source_path = band.path
            dest_path = source_path
            # TODO: rename bands to <ga_label>_<band>.tif
            if source_path.suffix == ".bin":
                dest_path = source_path.with_suffix(".tif")
            dest_path = ptype.rebase_path(image_path, package_directory, dest_path)
            _copy_file(source_path, dest_path, compress_imagery=True, hard_link=hard_link)
            after_file_copy(source_path, dest_path)
            band.path = dest_path

    if dataset.ancillary_files:
        for file_ in dataset.ancillary_files:
            source_path = file_.path
            dest_path = ptype.rebase_path(image_path, package_directory, source_path)
            _copy_file(source_path, dest_path, compress_imagery=True, hard_link=hard_link)
            after_file_copy(source_path, dest_path)
            file_.path = dest_path

    validate_metadata(dataset)

    # TODO: browse images

    target_checksums_path = target_path / GA_CHECKSUMS_FILE_NAME
    dataset.checksum_path = target_checksums_path

    target_metadata_path = serialise.write_dataset_metadata(target_path, dataset)

    checksums.add_file(target_metadata_path)
    checksums.write(target_checksums_path)

    return dataset
