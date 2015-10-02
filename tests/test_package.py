# coding=utf-8
from __future__ import absolute_import

from eodatasets import package, drivers, metadata, type as ptype
from tests import write_files, TestCase, assert_file_structure


class TestPackage(TestCase):
    def test_total_file_size(self):
        # noinspection PyProtectedMember
        f = write_files({
            'first.txt': 'test',
            'second.txt': 'test2'
        })

        self.assertEqual(9, package._file_size_bytes(*f.iterdir()))
