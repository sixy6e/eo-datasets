# coding=utf-8
from __future__ import absolute_import
import sys

from eodatasets import provenance
import eodatasets
from eodatasets.tests import TestCase


class ProvenanceTests(TestCase):
    def test_register_packages(self):
        d = provenance.SoftwareProvenance()

        d.note_software('rpm', 'vim', '1.2.3')

        self.assert_items_equal(
            [('rpm', 'vim', '1.2.3')],
            d.iter_software()
        )

    def test_register_python(self):
        d = provenance.SoftwareProvenance()

        d.note_python_packages('gdal', 'numpy')
        import pkg_resources

        self.assert_items_equal(
            [
                ('python', 'gdal', pkg_resources.require('gdal')[0].version),
                ('python', 'numpy', pkg_resources.require('numpy')[0].version)
            ],
            d.iter_software()
        )

    def test_global_defaults_apply(self):
        d = provenance.default_provenance()

        self.assert_values_equal(
            [
                ('python', 'eodatasets', eodatasets.__version__),
                ('python', 'python', '.'.join(map(str, sys.version_info)))
            ],
            d.iter_software()
        )

    def test_to_dict(self):
        parent = provenance.SoftwareProvenance()
        parent.note_software('a', 's1', 'v1')
        parent.note_software('a', 's3', 'v3')

        child = provenance.SoftwareProvenance(parent=parent)
        child.note_software('b', 's1', 'bv1')
        child.note_software('a', 's2', 'v2')

        # Parent should only contain own software.
        self.assertEqual(
            {
                'a': {'s1': 'v1', 's3': 'v3'}
            },
            parent.to_dict()
        )

        # Child should contain both parent and child software.
        self.assertEqual(
            {
                'a': {'s1': 'v1', 's2': 'v2', 's3': 'v3'},
                'b': {'s1': 'bv1'}
            },
            child.to_dict()
        )