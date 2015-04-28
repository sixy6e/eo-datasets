# coding=utf-8
"""
Tools for recording provenance of the current machine.
"""
from __future__ import absolute_import
import sys


class SoftwareProvenance(object):
    def __init__(self, parent=None):
        """
        :type parent: SoftwareProvenance
        """
        self.parent = parent

        #: :type: dict of (str, dict of (str, str))
        self.collections = {}

    def note_software(self, collection, name, version):
        if collection not in self.collections:
            self.collections[collection] = {}

        self.collections[collection][name] = version

    def note_python_packages(self, *names):
        import pkg_resources  # part of setuptools

        for name in names:
            version = pkg_resources.require(name)[0].version
            self.note_software('python', name, version)

    def note_rpm_packages(self, names):
        pass

    def iter_software(self):

        if self.parent:
            for s in self.parent.iter_software():
                yield s

        colletion_names = sorted(self.collections.keys())

        for collection_name in colletion_names:
            collection = self.collections[collection_name]

            software_names = sorted(collection.keys())

            for software_name in software_names:
                version = collection[software_name]
                yield collection_name, software_name, version

    def to_dict(self):
        d = {}

        for collection_name, software_name, version in self.iter_software():
            if collection_name not in d:
                d[collection_name] = {}

            d[collection_name][software_name] = version

        return d


def default_provenance():
    return SoftwareProvenance(parent=GLOBAL_PROVENANCE)


def _add_self(prov):
    # Add ourself.
    from eodatasets import __version__
    prov.note_software('python', 'eodatasets', __version__)


GLOBAL_PROVENANCE = SoftwareProvenance()
_add_self(GLOBAL_PROVENANCE)
GLOBAL_PROVENANCE.note_software('python', 'python', '.'.join(map(str, sys.version_info)))