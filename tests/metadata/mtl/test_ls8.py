# coding=utf-8
from __future__ import absolute_import
import unittest
import uuid
import datetime
import os

from pathlib import Path

import eodatasets.type as ptype
from tests.metadata.mtl import assert_expected_mtl


FILENAME = 'ls8_mtl.txt'

EXPECTED_OUT = ptype.DatasetMetadata(
    id_=uuid.UUID('3ff71eb0-d5c5-11e4-aebb-1040f381a756'),
    product_level='L1T',
    creation_dt=datetime.datetime(2014, 11, 12, 15, 8, 35),
    platform=ptype.PlatformMetadata(
        code='LANDSAT_8'
    ),
    instrument=ptype.InstrumentMetadata(
        name='OLI_TIRS'
    ),
    format_=ptype.FormatMetadata(
        name='GeoTIFF'
    ),
    acquisition=ptype.AcquisitionMetadata(
        groundstation=ptype.GroundstationMetadata(
            code='LGN'
        )
    ),
    usgs=ptype.UsgsMetadata(
        scene_id='LC81010782014285LGN00'
    ),
    extent=ptype.ExtentMetadata(
        coord=ptype.CoordPolygon(
            ul=ptype.Coord(
                lat=-24.98805,
                lon=133.97954
            ),
            ur=ptype.Coord(
                lat=-24.9864,
                lon=136.23866
            ),
            ll=ptype.Coord(
                lat=-26.99236,
                lon=133.96208
            ),
            lr=ptype.Coord(
                lat=-26.99055,
                lon=136.25985
            )
        ),
        center_dt=datetime.datetime(2014, 10, 12, 0, 56, 6, 5785)
    ),
    grid_spatial=ptype.GridSpatialMetadata(
        projection=ptype.ProjectionMetadata(
            geo_ref_points=ptype.PointPolygon(
                ul=ptype.Point(
                    x=397012.5,
                    y=7235987.5
                ),
                ur=ptype.Point(
                    x=625012.5,
                    y=7235987.5
                ),
                ll=ptype.Point(
                    x=397012.5,
                    y=7013987.5
                ),
                lr=ptype.Point(
                    x=625012.5,
                    y=7013987.5
                )
            ),
            datum='GDA94',
            ellipsoid='GRS80',
            map_projection='UTM',
            orientation='NORTH_UP',
            resampling_option='CUBIC_CONVOLUTION',
            zone=-53
        )
    ),
    image=ptype.ImageMetadata(
        satellite_ref_point_start=ptype.Point(x=101, y=78),
        cloud_cover_percentage=0.01,
        sun_azimuth=59.57807899,
        sun_elevation=57.89670734,
        sun_earth_distance=0.998137,
        ground_control_points_model=420,
        geometric_rmse_model=4.61,
        geometric_rmse_model_x=2.968,
        geometric_rmse_model_y=3.527,
        bands={}
    ),
    lineage=ptype.LineageMetadata(
        algorithm=ptype.AlgorithmMetadata(
            name='LPGS',
            version='2.3.0',
            parameters={}
        ),
        ancillary={
            'rlut': ptype.AncillaryMetadata(
                name='L8RLUT20130211_20431231v09.h5'
            ),
            'bpf_tirs': ptype.AncillaryMetadata(
                name='LT8BPF20141012002432_20141012011154.02'
            ),
            'bpf_oli': ptype.AncillaryMetadata(
                name='LO8BPF20141012002825_20141012011100.01'
            ),
            'cpf': ptype.AncillaryMetadata(
                name='L8CPF20141001_20141231.01'
            )}
    )
)


class TestMtlRead(unittest.TestCase):
    def test_ls8_equivalence(self):
        assert_expected_mtl(
            Path(os.path.join(os.path.dirname(__file__), FILENAME)),
            EXPECTED_OUT
        )
