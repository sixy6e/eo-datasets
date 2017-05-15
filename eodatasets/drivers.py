# coding=utf-8
from __future__ import absolute_import

import datetime
import logging
import re
import string
import xml.etree.cElementTree as etree
from copy import deepcopy

import yaml

try:
    from yaml import CSafeLoader as Loader
except ImportError:
    from yaml import Loader
from dateutil.parser import parse
from pathlib import Path

from eodatasets import type as ptype, metadata
from eodatasets.metadata import _GROUNDSTATION_LIST
from eodatasets.metadata import mdf, level1, adsfolder, rccfile, \
    passinfo, pds, npphdf5, image as md_image, gqa, valid_region

_LOG = logging.getLogger(__name__)


class DatasetDriver(object):
    def get_id(self):
        """
        A short identifier for this type of dataset.

        eg. 'nbar'

        :rtype: str
        """
        raise NotImplementedError()

    def fill_metadata(self, dataset, path, additional_files=()):
        """
        Populate the given dataset metadata from the path.

        :type additional_files: tuple[Path]
        :type dataset: ptype.DatasetMetadata
        :type path: Path
        """
        raise NotImplementedError()

    def get_ga_label(self, dataset):
        """
        Generate the GA Label ("dataset id") for a dataset.
        :type dataset:  ptype.DatasetMetadata
        :rtype: str
        """
        raise NotImplementedError()

    def expected_source(self):
        """
        Expected source dataset (driver).

        Also known as parent dataset.
        :rtype: DatasetDriver
        """
        raise NotImplementedError()

    def include_file(self, file_path):
        """
        Return true if source `file_path` should be included in package

        :param file_path: Source filename
        :rtype: boolean
        """
        return True

    def translate_path(self, dataset, file_path):
        """
        Translate an input filename if desired.

        :type dataset: ptype.DatasetMetadata
        :type file_path: Path
        :rtype: Path

        >>> # Test default behaviour: all files included unchanged.
        >>> DatasetDriver().translate_path(None, Path('/tmp/fake_path.TXT'))
        PosixPath('/tmp/fake_path.TXT')
        >>> DatasetDriver().translate_path(None, Path('/tmp/passinfo'))
        PosixPath('/tmp/passinfo')
        """
        # Default: no modification to filename.
        return file_path

    def to_band(self, dataset, path):
        """
        Create a band definition for the given output file.

        Return None if file should not be included as a band
        (the file will still be included in the package).

        :type dataset: ptype.DatasetMetadata
        :type path: Path
        :param path: The filename of the input file.
        :rtype: ptype.BandMetadata or None
        """
        raise NotImplementedError()

    def browse_image_bands(self, d):
        """
        Band ids for for an rgb browse image.
        :type d: ptype.DatasetMetadata
        :rtype (str, str, str)
        """
        # Defaults for satellites. Different products may override this.
        # These values come from the ARG25 spec.
        _satellite_browse_bands = {
            'LANDSAT_5': ('7', '4', '1'),
            'LANDSAT_7': ('7', '4', '1'),
            'LANDSAT_8': ('7', '5', '2'),
        }
        browse_bands = _satellite_browse_bands.get(d.platform.code)
        if not browse_bands:
            raise ValueError('Unknown browse bands for satellite %s' % d.platform.code)

        return browse_bands

    def calculate_valid_data_region(self, path, mask_value=None):
        image_files = [filename
                       for filename in path.rglob('*')
                       if self.include_file(filename)]
        return valid_region.safe_valid_region(image_files, mask_value)

    def __eq__(self, other):
        if self.__class__ != other.__class__:
            return False

        return self.__dict__ == other.__dict__


def get_groundstation_code(gsi):
    """
    Translate a GSI code into an EODS domain code.

    Domain codes are used in dataset_ids.

    It will also translate common gsi aliases if needed.

    :type gsi: str
    :rtype: str

    >>> get_groundstation_code('ASA')
    '002'
    >>> get_groundstation_code('HOA')
    '011'
    >>> # Aliases should work too.
    >>> get_groundstation_code('ALSP')
    '002'
    """
    groundstation = metadata.get_groundstation(gsi)
    if not groundstation:
        return None

    return groundstation.eods_domain_code


def _format_path_row(start_point, end_point=None):
    """
    Format path-row for display in a dataset id.

    :type start_point: ptype.Point or None
    :type end_point: ptype.Point or None
    :rtype: (str, str)

    >>> _format_path_row(ptype.Point(78, 132))
    ('078', '132')
    >>> _format_path_row(ptype.Point(12, 4))
    ('012', '004')
    >>> # Show the range of rows
    >>> _format_path_row(ptype.Point(78, 78), end_point=ptype.Point(78, 80))
    ('078', '078-080')
    >>> # Identical rows: don't show a range
    >>> _format_path_row(ptype.Point(78, 132), end_point=ptype.Point(78, 132))
    ('078', '132')
    >>> # This is odd behaviour, but we're doing it for consistency with the old codebases.
    >>> # Lack of path/rows are represented as single-digit zeros.
    >>> _format_path_row(None)
    ('0', '0')
    >>> _format_path_row(ptype.Point(None, None))
    ('0', '0')
    """
    if start_point is None:
        return '0', '0'

    def _format_val(val):
        if val:
            return '%03d' % val

        return '0'

    path = _format_val(start_point.x)
    rows = _format_val(start_point.y)

    # Add ending row if different.
    if end_point and start_point.y != end_point.y:
        rows += '-' + _format_val(end_point.y)

    return path, rows


def _get_process_code(dataset):
    """
    :type dataset: ptype.DatasetMetadata
    :return:
    """
    level = dataset.product_level

    if level:
        level = level.upper()

    orientation = None
    if dataset.grid_spatial and dataset.grid_spatial.projection:
        orientation = dataset.grid_spatial.projection.orientation

    if level == 'L1T':
        return 'OTH', 'P51'

    if orientation == 'NORTH_UP':
        if level == 'L1G':
            return 'SYS', 'P31'
        if level == 'L1GT':
            return 'OTH', 'P41'

    # Path
    if orientation in ('NOMINAL', 'NOM'):
        return 'SYS', 'P11'

    if dataset.ga_level == 'P00':
        return 'satellite_telemetry_data', 'P00'

    _LOG.warning('No process code mapped for level/orientation: %r, %r', level, orientation)
    return None, None


def _get_short_satellite_code(platform_code):
    """
    Get shortened form of satellite, as used in GA Dataset IDs. (eg. 'LS7')
    :param platform_code:
    :return:

    >>> _get_short_satellite_code('LANDSAT_8')
    'LS8'
    >>> _get_short_satellite_code('LANDSAT_5')
    'LS5'
    >>> _get_short_satellite_code('LANDSAT_7')
    'LS7'
    >>> _get_short_satellite_code('AQUA')
    'AQUA'
    >>> _get_short_satellite_code('TERRA')
    'TERRA'
    >>> _get_short_satellite_code('Invalid')
    Traceback (most recent call last):
    ...
    ValueError: Unknown platform code 'Invalid'
    """
    if platform_code.startswith('LANDSAT_'):
        return 'LS' + platform_code.split('_')[-1]

    if platform_code in ('AQUA', 'TERRA', 'NPP'):
        return platform_code

    raise ValueError('Unknown platform code %r' % platform_code)


def _fill_dataset_label(dataset, format_str, **additionals):
    path, row = _format_path_row(
        start_point=dataset.image.satellite_ref_point_start if dataset.image else None,
        end_point=dataset.image.satellite_ref_point_end if dataset.image else None
    )

    def _format_dt(d):
        if not d:
            return None
        return d.strftime("%Y%m%dT%H%M%S")

    def _format_day(dataset_):
        day = (dataset_.extent and dataset_.extent.center_dt) or \
              (dataset_.acquisition and dataset_.acquisition.aos)
        return day.strftime('%Y%m%d')

    level, ga_level = _get_process_code(dataset)

    if not ga_level:
        ga_level = dataset.ga_level

    station_code = None
    start = None
    end = None
    orbit = None
    if dataset.acquisition:
        if dataset.acquisition.groundstation:
            station_code = get_groundstation_code(dataset.acquisition.groundstation.code)
        if dataset.acquisition.aos:
            start = _format_dt(dataset.acquisition.aos)
        if dataset.acquisition.los:
            end = _format_dt(dataset.acquisition.los)

        orbit = dataset.acquisition.platform_orbit

    ancillary_quality = None
    if dataset.lineage:
        ancillary_quality = dataset.lineage.ancillary_quality

    formatted_params = {
        'satnumber': _get_short_satellite_code(dataset.platform.code),
        'sensor': _remove_chars(string.punctuation, dataset.instrument.name),
        'format': dataset.format_.name.upper(),
        'level': level,
        'galevel': ga_level,
        'usgs': dataset.usgs,
        'path': path,
        'rows': row,
        'orbit': orbit,
        'stationcode': station_code,
        'startdt': start,
        'ancillary_quality': ancillary_quality,
        'enddt': end,
        'rmsstring': dataset.rms_string,
        'day': _format_day(dataset),
    }
    formatted_params.update(additionals)
    return format_str.format(**formatted_params)


def _remove_chars(chars, s):
    """
    :param chars: string of characters to remove.
    :param s: input string
    :rtype: str

    >>> _remove_chars(string.punctuation, 'OLI_TIRS+')
    'OLITIRS'
    >>> _remove_chars('_', 'A_B_C')
    'ABC'
    >>> _remove_chars(string.punctuation, None)
    """
    if not s:
        return s
    return re.sub('[' + re.escape(''.join(chars)) + ']', '', s)


class RawDriver(DatasetDriver):
    def get_id(self):
        return 'satellite_telemetry_data'

    def expected_source(self):
        # Raw dataset has no source.
        return None

    def get_ga_label(self, dataset):
        """
        :type dataset: ptype.DatasetMetadata
        :rtype: str
        """
        _LOG.info('Labelling dataset: %r', dataset)
        # Examples for each Landsat raw:
        # 'LS8_OLITIRS_STD-MD_P00_LC81160740742015089ASA00_116_074-084_20150330T022553Z20150330T022657'
        # 'LS7_ETM_STD-RCC_P00_L7ET2005007020028ASA123_0_0_20050107T020028Z20050107T020719'
        # 'LS5_TM_STD-RCC_P00_L5TB2005152015110ASA111_0_0_20050601T015110Z20050107T020719'

        # Raw datasets have a strange extra column derived from ADS folder names.
        # It's an interval id for Landsat products, and mixtures of orbits/rms-strings otherwise.
        folder_identifier = []
        if dataset.usgs:
            folder_identifier.append(dataset.usgs.interval_id)
        else:
            if dataset.acquisition.platform_orbit:
                folder_identifier.append(str(dataset.acquisition.platform_orbit))
            if dataset.rms_string:
                folder_identifier.append(dataset.rms_string)
            if dataset.acquisition.groundstation:
                folder_identifier.append(dataset.acquisition.groundstation.code)

        return _fill_dataset_label(
            dataset,
            '{satnumber}_{sensor}_STD-{format}_P00_{folderident}_{path}_{rows}_{startdt}Z{enddt}',
            folderident='.'.join(folder_identifier)
        )

    def fill_metadata(self, dataset, path, additional_files=()):
        """
        :type additional_files: tuple[Path]
        :type dataset: ptype.DatasetMetadata
        :type path: Path
        :rtype: ptype.DatasetMetadata
        """
        dataset = adsfolder.extract_md(dataset, path)
        dataset = rccfile.extract_md(dataset, path)
        dataset = mdf.extract_md(dataset, path)
        dataset = passinfo.extract_md(dataset, path)
        dataset = pds.extract_md(dataset, path)
        dataset = npphdf5.extract_md(dataset, path)

        # TODO: Antenna coords for groundstation? Heading?
        # TODO: Bands? (or eg. I/Q files?)
        return dataset

    def to_band(self, dataset, path):
        # We don't record any bands for a raw dataset (yet?)
        return None


class OrthoDriver(DatasetDriver):
    def get_id(self):
        return 'level1'

    def expected_source(self):
        return RawDriver()

    def fill_metadata(self, dataset, path, additional_files=()):
        """
        :type additional_files: tuple[Path]
        :type dataset: ptype.DatasetMetadata
        :type path: Path
        :rtype: ptype.DatasetMetadata
        """
        dataset = level1.populate_level1(dataset, path, additional_files)
        dataset = gqa.choose_and_populate_gqa(dataset, additional_files)
        return dataset

    def include_file(self, file_path):
        """
        Exclude .aux.xml paths
        :param file_path:
        :return:

        >>> OrthoDriver().include_file(Path('something.TIF.aux.xml'))
        False
        >>> OrthoDriver().include_file(Path('LC81120792014026ASA00_B5.TIF'))
        True
        """
        return not file_path.name.endswith('.aux.xml')

    def to_band(self, dataset, path):
        """
        :type dataset: ptype.DatasetMetadata
        :type path: pathlib.Path
        :rtype: ptype.BandMetadata

        >>> OrthoDriver().to_band(None, Path('/tmp/out/LT51030782005002ASA00_B3.TIF'))
        BandMetadata(path=PosixPath('/tmp/out/LT51030782005002ASA00_B3.TIF'), number='3')
        >>> OrthoDriver().to_band(None, Path('/tmp/out/LC81090852015088LGN00_B10.tif'))
        BandMetadata(path=PosixPath('/tmp/out/LC81090852015088LGN00_B10.tif'), number='10')
        >>> OrthoDriver().to_band(None, Path('/data/output/LE70900782007292ASA00_B6_VCID_2.TIF'))
        BandMetadata(path=PosixPath('/data/output/LE70900782007292ASA00_B6_VCID_2.TIF'), number='6_vcid_2')
        >>> # No bands for non-tiff files.
        >>> OrthoDriver().to_band(None, Path('/tmp/out/LC81090852015088LGN00_MTL.txt'))
        >>> OrthoDriver().to_band(None, Path('/tmp/out/passinfo'))
        >>> # A DEM image -- not included as a band.
        >>> OrthoDriver().to_band(None, Path('LT05_L1TP_108078_20060703_20170309_01_T1_DEM.TIF'))
        """
        if path.suffix.lower() != '.tif':
            return None

        name = path.stem.lower()

        # A DEM image -- the only tif without a 'B' prefix.
        # We don't include it in the list of bands according to Lan-Wei, as it's not part of a typical USGS package.
        if name.endswith('_dem'):
            return None

        # Images end in a band number (eg '_B12.tif'). Extract it.
        position = name.rfind('_b')
        if position == -1:
            raise ValueError('Unexpected tif image in level1: %r' % path)
        band_number = name[position + 2:]

        return ptype.BandMetadata(path=path, number=band_number)

    def get_ga_label(self, dataset):
        # Examples:
        # "LS8_OLITIRS_OTH_P41_GALPGS01-002_101_078_20141012"
        # "LS7_ETM_SYS_P31_GALPGS01-002_114_73_20050107"
        #     "LS5_TM_OTH_P51_GALPGS01-002_113_063_20050601"

        # Definitive is considered normal (unflagged), otherwise we flag the ancillary quality.
        ancillary_flag = ''
        if dataset.lineage and dataset.lineage.ancillary_quality and dataset.lineage.ancillary_quality != 'DEFINITIVE':
            ancillary_flag = '-' + dataset.lineage.ancillary_quality

        return _fill_dataset_label(
            dataset,
            '{satnumber}_{sensor}_{level}_{galevel}{ancillary_flag}_GALPGS01-{stationcode}_{path}_{rows}_{day}',
            ancillary_flag=ancillary_flag,
        )


def borrow_single_sourced_fields(dataset, source_dataset):
    """
    Copy common metadata fields from a source dataset.

    The fields copied assume a non-composite dataset with only one source.

    :type dataset: ptype.DatasetMetadata
    :type source_dataset: ptype.DatasetMetadata
    :rtype: ptype.DatasetMetadata
    """

    if not dataset.image:
        dataset.image = ptype.ImageMetadata(bands={})
    if not dataset.extent:
        dataset.extent = ptype.ExtentMetadata()
    dataset.extent.steal_fields_from(source_dataset.extent)
    dataset.platform = source_dataset.platform
    dataset.instrument = source_dataset.instrument
    if not dataset.acquisition:
        dataset.acquisition = ptype.AcquisitionMetadata()
    dataset.acquisition.steal_fields_from(source_dataset.acquisition)
    if not dataset.image.satellite_ref_point_start:
        dataset.image.satellite_ref_point_start = source_dataset.image.satellite_ref_point_start
        dataset.image.satellite_ref_point_end = source_dataset.image.satellite_ref_point_end

    return dataset


class NbarDriver(DatasetDriver):
    METADATA_FILE = 'nbar-metadata.yaml'
    product_ids = {'brdf': 'nbar',
                   'terrain': 'nbart',
                   'lambertian': 'lambertian'}

    def __init__(self, subset_name):
        # Subset is typically "brdf" or "terrain" -- which NBAR portion to package.
        self.product_id = self.product_ids[subset_name]
        self.subset_name = subset_name

    def get_id(self):
        return self.product_id

    def expected_source(self):
        return OrthoDriver()

    def get_ga_label(self, dataset):
        # Example: LS8_OLITIRS_NBAR_P51_GALPGS01-032_090_085_20140115

        return _fill_dataset_label(
            dataset,
            '{satnumber}_{sensor}_{nbartype}_{galevel}_GA{nbartype}01-{stationcode}_{path}_{rows}_{day}',
            nbartype=self.product_id.upper()
        )

    def _read_band_number(self, file_path):
        """
        :type file_path: Path
        :return:
        >>> NbarDriver('brdf')._read_band_number(Path('reflectance_brdf_2.tif'))
        '2'
        >>> NbarDriver('terrain')._read_band_number(Path('reflectance_terrain_7.tif'))
        '7'
        >>> p = Path('/tmp/something/LS8_OLITIRS_NBAR_P54_GANBAR01-002_112_079_20140126_B4.tif')
        >>> NbarDriver('brdf')._read_band_number(p)
        '4'
        """
        number = file_path.stem.split('-')[-1].lower()

        if number.startswith('b'):
            return number[1:]

        return number

    def include_file(self, file_path):
        """
        :param file_path:
        :rtype: boolean
        >>> NbarDriver('terrain').include_file(Path('Reflectance_output/reflectance_terrain_7.tif'))
        True
        >>> NbarDriver('brdf').include_file(Path('Reflectance_output/reflectance_terrain_7.tif'))
        False
        """
        # Skip hidden files and envi headers. (envi files are converted to tif during copy)
        return (file_path.suffix == '.tif' and
                file_path.name.startswith('%s-reflectance' % self.subset_name))

    def translate_path(self, dataset, file_path):
        """
        :type dataset: ptype.DatasetMetadata
        :type file_path: Path
        :rtype: Path
        >>> from tests.metadata.mtl.test_ls8 import EXPECTED_OUT as ls8_dataset
        >>> NbarDriver('terrain').translate_path(ls8_dataset, Path('Reflectance_output/reflectance_terrain_7.tif'))
        PosixPath('LS8_OLITIRS_NBART_P51_GANBART01-032_101_078_20141012_B7.tif')
        """

        ga_label = self.get_ga_label(dataset)
        band_number = self._read_band_number(file_path)

        return Path('%s_B%s.tif' % (ga_label, band_number))

    def to_band(self, dataset, path):
        """
        :type dataset: ptype.DatasetMetadata
        :type path: Path
        :rtype: ptype.BandMetadata

        >>> p = Path('/tmp/something/reflectance_terrain_3.tif')
        >>> NbarDriver('terrain').to_band(None, p).number
        '3'
        >>> NbarDriver('terrain').to_band(None, p).path
        PosixPath('/tmp/something/reflectance_terrain_3.tif')
        >>> p = Path('/tmp/something/LS8_OLITIRS_NBAR_P54_GANBART01-002_112_079_20140126_B4.tif')
        >>> NbarDriver('terrain').to_band(None, p).number
        '4'
        """
        return ptype.BandMetadata(path=path, number=_read_band_number(path))

    def fill_metadata(self, dataset, path, additional_files=()):
        """
        :type additional_files: tuple[Path]
        :type dataset: ptype.DatasetMetadata
        :type path: Path
        :rtype: ptype.DatasetMetadata
        """

        with open(str(path.joinpath('metadata', self.METADATA_FILE))) as f:
            nbar_metadata = yaml.load(f, Loader=Loader)

        # Copy relevant fields from source ortho.
        if 'level1' in dataset.lineage.source_datasets:
            source_ortho = dataset.lineage.source_datasets['level1']
            borrow_single_sourced_fields(dataset, source_ortho)

            # TODO, it'd be better to grab this from the images, but they're generated after
            # this code is run. Copying from Source will do for now
            dataset.grid_spatial = deepcopy(dataset.lineage.source_datasets['level1'].grid_spatial)

            dataset.grid_spatial.projection.valid_data = self.calculate_valid_data_region(path)

        if not dataset.lineage:
            dataset.lineage = ptype.LineageMetadata()

        self._fill_algorithm_information(dataset, nbar_metadata['algorithm_information'])

        dataset.product_doi = nbar_metadata['algorithm_information']['arg25_doi']

        # Extract ancillary file data and values
        parameters = {}

        ancils = nbar_metadata['ancillary_data']
        brdfs = ancils.pop('brdf', {})
        brdf_ancils = {'_'.join((band_name, 'brdf', ancil_type)): values
                       for band_name, ancil_types in brdfs.items()
                       for ancil_type, values in ancil_types.items()}
        ancils.update(brdf_ancils)

        # Add algorithm parameters
        for name, values in ancils.items():
            parameters[name] = values['value']
        if parameters:
            dataset.lineage.algorithm.parameters = parameters

        # Add ancillary files
        ancil_files = {}
        for name, values in ancils.items():
            if 'data_file' not in values:
                continue
            ancil_files[name] = ptype.AncillaryMetadata(
                type_=name,
                name=values['data_file'].rpartition('/')[2],
                uri=values['data_file'],
                file_owner=values['user'],
                # PyYAML parses these as datetimes already.
                access_dt=values['accessed'],
                modification_dt=values['modified']
            )

        if ancil_files:
            dataset.lineage.ancillary = ancil_files

        # All NBARs are P54. (source: Lan Wei)
        dataset.ga_level = 'P54'
        dataset.format_ = ptype.FormatMetadata('GeoTIFF')

        return dataset

    def _fill_algorithm_information(self, dataset, alg_src_info):
        alg_meta = ptype.AlgorithmMetadata(name=self.subset_name,
                                           version=str(alg_src_info['algorithm_version']))
        if self.subset_name == 'brdf':
            alg_meta.doi = alg_src_info['nbar_doi']
        else:
            alg_meta.doi = alg_src_info['nbar_terrain_corrected_doi']

        dataset.lineage.algorithm = alg_meta


def _read_band_number(file_path):
    """
    :type file_path: Path
    :return:
    >>> _read_band_number(Path('reflectance_brdf_2.tif'))
    '2'
    >>> _read_band_number(Path('reflectance_terrain_7.tif'))
    '7'
    >>> p = Path('/tmp/something/LS8_OLITIRS_NBAR_P54_GALPGS01-002_112_079_20140126_B4.tif')
    >>> _read_band_number(p)
    '4'
    """
    number = file_path.stem.split('_')[-1].lower()

    if number.startswith('b'):
        return number[1:]

    return number


class EODSDriver(DatasetDriver):
    """
    A legacy dataset in eods-package format (ie. a scene01 directory).

    We read whatever metadata we can.
    """

    def get_id(self):
        return "EODS"

    def expected_source(self):
        """
        EODS Datasets typically have no sources: their exact provenance was not recorded.
        :rtype: DatasetDriver
        """
        return None

    def get_ga_label(self, dataset):
        return dataset.ga_label

    def to_band(self, dataset, path):
        """
        :type dataset: ptype.DatasetMetadata
        :type final_path: pathlib.Path
        :rtype: ptype.BandMetadata
        """
        if path.suffix.lower() != '.tif':
            return None

        name = path.stem
        # Images end in a band number (eg '_B12.tif'). Extract it.
        position = name.rfind('_')
        if position == -1:
            raise ValueError('Unexpected tif image in eods: %r' % path)
        if re.match(r"[Bb]\d+", name[position + 1:]):
            band_number = name[position + 2:]
        else:
            band_number = name[position + 1:]

        return ptype.BandMetadata(path=path, number=band_number)

    def fill_metadata(self, dataset, path, additional_files=()):
        """
        :type additional_files: tuple[Path]
        :type dataset: ptype.DatasetMetadata
        :type path: Path
        :rtype: ptype.DatasetMetadata
        """

        fields = re.match(
            (
                r"(?P<vehicle>LS[578])"
                r"_(?P<instrument>OLI_TIRS|OLI|TIRS|TM|ETM)"
                r"_(?P<type>NBAR|PQ|FC)"
                r"_(?P<level>[^-_]*)"
                r"_(?P<product>[^-_]*)"
                r"-(?P<groundstation>[0-9]{3})"
                r"_(?P<path>[0-9]{3})"
                r"_(?P<row>[0-9]{3})"
                r"_(?P<date>[12][0-9]{7})"
                r"(_(?P<version>[0-9]+))?"
                "$"
            ),
            path.stem).groupdict()

        dataset.product_type = "EODS_" + fields["type"]
        dataset.ga_level = fields["level"]
        dataset.ga_label = path.stem
        dataset.format_ = ptype.FormatMetadata(name='GeoTiff')

        if not dataset.platform:
            dataset.platform = ptype.PlatformMetadata()
        dataset.platform.code = "LANDSAT_" + fields["vehicle"][2]

        if not dataset.instrument:
            dataset.instrument = ptype.InstrumentMetadata()
        dataset.instrument.name = fields["instrument"]

        if not dataset.image:
            dataset.image = ptype.ImageMetadata(bands={})
        dataset.image.satellite_ref_point_start = ptype.Point(int(fields["path"]), int(fields["row"]))
        dataset.image.satellite_ref_point_end = ptype.Point(int(fields["path"]), int(fields["row"]))

        for image_path in path.joinpath("scene01").iterdir():
            band = self.to_band(dataset, image_path)
            if band:
                dataset.image.bands[band.number] = band
        md_image.populate_from_image_metadata(dataset)

        if not dataset.acquisition:
            dataset.acquisition = ptype.AcquisitionMetadata()

        for _station in _GROUNDSTATION_LIST:
            if _station["eods_domain_code"] == fields["groundstation"]:
                dataset.acquisition.groundstation = ptype.GroundstationMetadata(code=_station["code"])
                break

        if not dataset.extent:
            dataset.extent = ptype.ExtentMetadata()

        def els2date(els):
            if not els:
                return None
            return parse(els[0].text)

        doc = etree.parse(str(path.joinpath('metadata.xml')))
        aos = els2date(doc.findall("./ACQUISITIONINFORMATION/EVENT/AOS"))
        los = els2date(doc.findall("./ACQUISITIONINFORMATION/EVENT/LOS"))
        start_time = els2date(doc.findall("./EXEXTENT/TEMPORALEXTENTFROM"))
        end_time = els2date(doc.findall("./EXEXTENT/TEMPORALEXTENTTO"))

        # check if the dates in the metadata file are at least as accurate as what we have
        filename_time = datetime.datetime.strptime(fields["date"], "%Y%m%d")
        time_diff = start_time - filename_time

        # Is the EODS metadata extremely off?
        if abs(time_diff).days != 0:
            raise ValueError('EODS time information differs too much from source files: %s' % time_diff)

        dataset.acquisition.aos = aos
        dataset.acquisition.los = los
        dataset.extent.center_dt = start_time + (end_time - start_time) / 2
        dataset.extent.from_dt = start_time
        dataset.extent.to_dt = end_time
        return dataset


class PqaDriver(DatasetDriver):
    METADATA_FILE = 'pq-metadata.yaml'

    def get_id(self):
        return 'pqa'

    def expected_source(self):
        return (OrthoDriver(), NbarDriver('brdf'))

    def get_ga_label(self, dataset):
        # Eg. 'LS8_OLI_TIRS_PQ_P55_GAPQ01-032_090_081_20140726'
        return _fill_dataset_label(
            dataset,
            '{satnumber}_{sensor}_PQ_{galevel}_GAPQ01-{stationcode}_{path}_{rows}_{day}',
        )

    def fill_metadata(self, dataset, path, additional_files=()):
        """
        :type additional_files: tuple[Path]
        :type dataset: ptype.DatasetMetadata
        :type path: Path
        :rtype: ptype.DatasetMetadata
        """
        dataset.ga_level = 'P55'

        # Copy relevant fields from source nbar.
        if 'nbar' in dataset.lineage.source_datasets:
            source_ortho = dataset.lineage.source_datasets['nbar']
            borrow_single_sourced_fields(dataset, source_ortho)

            # TODO, it'd be better to grab this from the images, but they're generated after
            # this code is run. Copying from Source will do for now
            dataset.grid_spatial = deepcopy(dataset.lineage.source_datasets['nbar'].grid_spatial)

            contiguous_data_bit = 0b100000000

            dataset.grid_spatial.projection.valid_data = self.calculate_valid_data_region(path, contiguous_data_bit)

        dataset.format_ = ptype.FormatMetadata('GeoTIFF')

        with open(str(path.joinpath('metadata', self.METADATA_FILE))) as f:
            pq_metadata = yaml.load(f, Loader=Loader)

        if not dataset.lineage:
            dataset.lineage = ptype.LineageMetadata()

        dataset.lineage.algorithm = ptype.AlgorithmMetadata(
            name='pqa',
            version=str(pq_metadata['algorithm_information']['software_version']),
            doi=pq_metadata['algorithm_information']['pq_doi'])

        # Add ancillary files
        ancils = pq_metadata['ancillary']
        ancil_files = {}
        for name, values in ancils.items():
            ancil_files[name] = ptype.AncillaryMetadata(
                type_=name,
                name=values['data_source'],
                uri=values['data_file'],
                file_owner=values['user'],
                # PyYAML parses these as datetimes already.
                access_dt=values['accessed'],
                modification_dt=values['modified']
            )

        if ancil_files:
            dataset.lineage.ancillary = ancil_files

        product_flags = {}
        # Record which tests where run in 'product_flags'
        for test_name, val in pq_metadata['tests_run'].items():
            product_flags['tested_%s' % test_name] = val

        dataset.product_flags = product_flags

        return dataset

    def include_file(self, file_path):
        return (file_path.suffix.lower() == '.tif' and
                file_path.name.startswith('pixel-quality'))

    def translate_path(self, dataset, file_path):
        """
        :type dataset: ptype.DatasetMetadata
        :type file_path: pathlib.Path
        :return:
        """
        # Rename to contain the ga_label.
        suffix = file_path.suffix.lower()
        if suffix == '.tif':
            ga_label = self.get_ga_label(dataset)
            return file_path.with_name(ga_label + suffix)

        return file_path

    def to_band(self, dataset, path):
        """
        :type dataset: ptype.DatasetMetadata
        :type path: Path
        :param path: The filename of the input file.
        :rtype: ptype.BandMetadata
        """
        if path.suffix != '.tif':
            return None

        return ptype.BandMetadata(path=path, number='pqa')

    def browse_image_bands(self, d):
        return 'pqa',


PACKAGE_DRIVERS = {
    'raw': RawDriver(),
    'pqa': PqaDriver(),
    'level1': OrthoDriver(),
    'nbar': NbarDriver('brdf'),
    'nbart': NbarDriver('terrain'),
    'lambertian': NbarDriver('lambertian'),
    'eods': EODSDriver(),
    # Backwards compat.
    'ortho': OrthoDriver(),
}
