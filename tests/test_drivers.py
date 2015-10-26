# coding=utf-8
from __future__ import absolute_import
import datetime
import copy
from uuid import UUID

from pathlib import Path

from eodatasets import drivers
from tests.metadata.mtl import test_ls8, test_ls7_definitive, test_ls5_definitive
from tests import write_files, TestCase
import eodatasets.type as ptype

_LS5_RAW = ptype.DatasetMetadata(
    id_=UUID('c86809b3-e894-11e4-8958-1040f381a756'),
    ga_level='P00',
    product_type='satellite_telemetry_data',
    creation_dt=datetime.datetime(2015, 4, 22, 0, 7, 48),
    size_bytes=5871413760,
    checksum_path=Path('package.sha1'),
    platform=ptype.PlatformMetadata(code='LANDSAT_5'),
    instrument=ptype.InstrumentMetadata(name='TM', operation_mode='BUMPER'),
    format_=ptype.FormatMetadata(name='RCC'),
    acquisition=ptype.AcquisitionMetadata(
        aos=datetime.datetime(2005, 6, 1, 1, 51, 10),
        los=datetime.datetime(2005, 6, 1, 2, 0, 25),
        groundstation=ptype.GroundstationMetadata(code='ASA'),
        platform_orbit=113025
    ),
    usgs=ptype.UsgsMetadata(
        interval_id='L5TB2005152015110ASA111'
    ),
    lineage=ptype.LineageMetadata(
        machine=ptype.MachineMetadata(
            hostname='niggle.local',
            runtime_id=UUID('b2af5545-e894-11e4-b3b0-1040f381a756'),
            type_id='jobmanager',
            version='2.4.0',
            uname='Darwin niggle.local 14.3.0 Darwin Kernel Version 14.3.0: Mon Mar 23 11:59:05 PDT 2015; '
                  'root:xnu-2782.20.48~5/RELEASE_X86_64 x86_64'
        ),
        source_datasets={}
    )
)

_LS7_RAW = ptype.DatasetMetadata(
    id_=UUID('c50c6bd4-e895-11e4-9814-1040f381a756'),
    ga_level='P00',
    product_type='satellite_telemetry_data',
    creation_dt=datetime.datetime(2015, 4, 15, 1, 42, 47),
    size_bytes=7698644992,
    checksum_path=Path('package.sha1'),
    usgs=ptype.UsgsMetadata(
        interval_id='L7ET2005007020028ASA123'
    ),
    platform=ptype.PlatformMetadata(code='LANDSAT_7'),
    instrument=ptype.InstrumentMetadata(name='ETM', operation_mode='SAM'),
    format_=ptype.FormatMetadata(name='RCC'),
    acquisition=ptype.AcquisitionMetadata(
        aos=datetime.datetime(2005, 1, 7, 2, 0, 28),
        los=datetime.datetime(2005, 1, 7, 2, 7, 19),
        groundstation=ptype.GroundstationMetadata(code='ASA'),
        platform_orbit=30486
    ),
    lineage=ptype.LineageMetadata(
        machine=ptype.MachineMetadata(
            hostname='niggle.local',
            runtime_id=UUID('a86f8a4c-e895-11e4-83e1-1040f381a756'),
            type_id='jobmanager',
            version='2.4.0',
            uname='Darwin niggle.local 14.3.0 Darwin Kernel Version 14.3.0: Mon Mar 23 '
                  '11:59:05 PDT 2015; root:xnu-2782.20.48~5/RELEASE_X86_64 x86_64'
        ),
        source_datasets={}
    )
)

_EXPECTED_NBAR = ptype.DatasetMetadata(
    id_=UUID('c50c6bd4-e895-11e4-9814-1040f381a756'),
    ga_level='P54',
    ga_label='LS8_OLITIRS_TNBAR_P54_GALPGS01-032_101_078_20141012',
    product_type='nbar_terrain',
    platform=ptype.PlatformMetadata(code='LANDSAT_8'),
    instrument=ptype.InstrumentMetadata(name='OLI_TIRS'),
    format_=ptype.FormatMetadata(name='GeoTIFF'),
    acquisition=ptype.AcquisitionMetadata(groundstation=ptype.GroundstationMetadata(code='LGN')),
    extent=ptype.ExtentMetadata(
        coord=ptype.CoordPolygon(
            ul=ptype.Coord(lat=-24.98805, lon=133.97954),
            ur=ptype.Coord(lat=-24.9864, lon=136.23866),
            ll=ptype.Coord(lat=-26.99236, lon=133.96208),
            lr=ptype.Coord(lat=-26.99055, lon=136.25985)
        ),
        center_dt=datetime.datetime(2014, 10, 12, 0, 56, 6, 5785)
    ),
    image=ptype.ImageMetadata(
        satellite_ref_point_start=ptype.Point(x=101, y=78),
        bands={}
    ),
    lineage=ptype.LineageMetadata(
        source_datasets={'ortho': test_ls8.EXPECTED_OUT}
    )
)


_EXPECTED_PQA = ptype.DatasetMetadata(
    id_=UUID('c50c6bd4-e895-11e4-9814-1040f381a756'),
    ga_level='P55',
    product_type='pqa',
    ga_label='LS8_OLITIRS_PQ_P55_GAPQ01-032_101_078_20141012',
    platform=ptype.PlatformMetadata(code='LANDSAT_8'),
    instrument=ptype.InstrumentMetadata(name='OLI_TIRS'),
    format_=ptype.FormatMetadata(name='GeoTIFF'),
    acquisition=ptype.AcquisitionMetadata(groundstation=ptype.GroundstationMetadata(code='LGN')),
    extent=ptype.ExtentMetadata(
        coord=ptype.CoordPolygon(
            ul=ptype.Coord(lat=-24.98805, lon=133.97954),
            ur=ptype.Coord(lat=-24.9864, lon=136.23866),
            ll=ptype.Coord(lat=-26.99236, lon=133.96208),
            lr=ptype.Coord(lat=-26.99055, lon=136.25985)
        ),
        center_dt=datetime.datetime(2014, 10, 12, 0, 56, 6, 5785)
    ),
    image=ptype.ImageMetadata(
        satellite_ref_point_start=ptype.Point(x=101, y=78),
        bands={}
    ),
    lineage=ptype.LineageMetadata(
        source_datasets={'nbar_brdf': _EXPECTED_NBAR}
    )
)



class TestDrivers(TestCase):
    def _get_raw_ls8(self):
        d = write_files({
            'LANDSAT-8.11308': {
                'LC81160740842015089ASA00': {
                    '480.000.2015089022657325.ASA': '',
                    '481.000.2015089022653346.ASA': '',
                    'LC81160740742015089ASA00_IDF.xml': '',
                    'LC81160740742015089ASA00_MD5.txt': '',
                    'file.list': '',
                }
            }
        })
        raw_driver = drivers.RawDriver()
        metadata = raw_driver.fill_metadata(
            ptype.DatasetMetadata(),
            d.joinpath('LANDSAT-8.11308', 'LC81160740842015089ASA00')
        )
        return metadata, raw_driver

    def test_raw_ls8_time_calc(self):
        metadata, raw_driver = self._get_raw_ls8()

        self.assertEqual(metadata.platform.code, 'LANDSAT_8')
        self.assertEqual(metadata.instrument.name, 'OLI_TIRS')

        # TODO: Can we extract the operation mode?
        self.assertEqual(metadata.instrument.operation_mode, None)

        self.assertEqual(metadata.acquisition.platform_orbit, 11308)
        self.assertEqual(metadata.acquisition.groundstation.code, 'ASA')

        # Note that the files are not in expected order: when ordered by their first number (storage location), the
        # higher number is actually an earlier date.
        self.assertEqual(metadata.acquisition.aos, datetime.datetime(2015, 3, 30, 2, 25, 53, 346000))
        self.assertEqual(metadata.acquisition.los, datetime.datetime(2015, 3, 30, 2, 26, 57, 325000))

    def test_eods_fill_metadata(self):
        dataset_folder = "LS8_OLI_TIRS_NBAR_P54_GANBAR01-015_101_078_20141012"
        bandname = '10'
        bandfile = dataset_folder+'_B'+bandname+'.tif'
        input_folder = write_files({
            dataset_folder: {
                'metadata.xml': """<EODS_DATASET>
                <ACQUISITIONINFORMATION>
                <EVENT>
                <AOS>20141012T03:23:36</AOS>
                <LOS>20141012T03:29:10</LOS>
                </EVENT>
                </ACQUISITIONINFORMATION>
                <EXEXTENT>
                <TEMPORALEXTENTFROM>20141012 00:55:54</TEMPORALEXTENTFROM>
                <TEMPORALEXTENTTO>20141012 00:56:18</TEMPORALEXTENTTO>
                </EXEXTENT>
                </EODS_DATASET>""",
                'scene01': {
                    bandfile: ''
                }
            }
        })
        expected = ptype.DatasetMetadata(
            id_=_EXPECTED_NBAR.id_,
            ga_label=dataset_folder,
            ga_level='P54',
            product_type='EODS_NBAR',
            platform=ptype.PlatformMetadata(code='LANDSAT_8'),
            instrument=ptype.InstrumentMetadata(name='OLI_TIRS'),
            format_=ptype.FormatMetadata(name='GeoTiff'),
            acquisition=ptype.AcquisitionMetadata(aos=datetime.datetime(2014, 10, 12, 3, 23, 36),
                                                  los=datetime.datetime(2014, 10, 12, 3, 29, 10),
                                                  groundstation=ptype.GroundstationMetadata(code='LGS')),
            extent=ptype.ExtentMetadata(center_dt=datetime.datetime(2014, 10, 12, 0, 56, 6)),
            image=ptype.ImageMetadata(satellite_ref_point_start=ptype.Point(x=101, y=78),
                                      satellite_ref_point_end=ptype.Point(x=101, y=78),
                                      bands={bandname: ptype.BandMetadata(number=bandname,
                                                                    path=Path(input_folder, dataset_folder,
                                                                              'scene01', bandfile))}),
            ancillary_files=[ptype.AncillaryFile(type_='xml', path=Path(input_folder, dataset_folder, 'metadata.xml'))]
        )
        dataset = ptype.DatasetMetadata(
            id_=_EXPECTED_NBAR.id_
        )
        received = drivers.EODSDriver().fill_metadata(dataset, input_folder.joinpath(dataset_folder))
        self.assertEqual(expected, received)

    def test_nbar_fill_metadata(self):
        input_folder = write_files({
            'reflectance_brdf_1.bin': '',
            'reflectance_brdf_1.hdr': '',
            'reflectance_brdf_1.bin.aux.xml': '',
            'reflectance_terrain_1.bin': '',
            'reflectance_terrain_1.bin.aux.xml': '',
            'reflectance_terrain_1.hdr': '',
        })
        dataset = ptype.DatasetMetadata(
            id_=_EXPECTED_NBAR.id_,
            lineage=ptype.LineageMetadata(
                source_datasets={
                    'ortho': test_ls8.EXPECTED_OUT
                }
            )
        )
        expected = copy.deepcopy(_EXPECTED_NBAR)
        expected.image.bands = {
            '1': ptype.BandMetadata(number='1', path=Path(input_folder, 'reflectance_terrain_1.bin'))
        }
        expected.ancillary_files = [
            ptype.AncillaryFile(type_='header', path=Path(input_folder, 'reflectance_terrain_1.hdr'))
        ]
        received = drivers.NbarDriver('terrain').fill_metadata(dataset, input_folder)
        self.assert_same(expected, received)


    def test_pqa_fill(self):
        input_folder = write_files({
            'band.tif': ''
        })

        dataset = ptype.DatasetMetadata(
            id_=_EXPECTED_PQA.id_,
            lineage=ptype.LineageMetadata(
                source_datasets={
                    'nbar_brdf': _EXPECTED_NBAR
                }
            )
        )

        expected = copy.deepcopy(_EXPECTED_PQA)
        expected.image.bands = {
            'pqa': ptype.BandMetadata(number='pqa', path=Path(input_folder, 'band.tif'))
        }

        received = drivers.PqaDriver().fill_metadata(dataset, input_folder)

        self.assert_same(expected, received)

    def test_pqa_to_band(self):
        input_folder = write_files({
            'pqa.tif': '',
            'process.log': '',
            'passinfo': '',
        })

        # Creates a single band.
        self.assertEqual(
            [ptype.BandMetadata(path=input_folder.joinpath('pqa.tif'), number='pqa')],
            drivers.PqaDriver().to_bands(input_folder.joinpath('pqa.tif'))
        )

        # Other files should not be bands.
        self.assertIsNone(drivers.PqaDriver().to_bands(input_folder.joinpath('process.log')))
        self.assertIsNone(drivers.PqaDriver().to_bands(input_folder.joinpath('passinfo')))
