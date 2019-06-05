import subprocess
import tempfile
from pathlib import Path
from subprocess import check_call
from typing import Dict, Tuple
from typing import Sequence, Union, Generator

import attr
import h5py
import numpy
import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS
from rasterio.enums import Resampling

LEVELS = [8, 16, 32]


def run_command(command: Sequence[Union[str, Path]], work_dir: Path) -> None:
    check_call([str(s) for s in command], cwd=str(work_dir))


@attr.s(auto_attribs=True, slots=True, hash=True, frozen=True)
class GridSpec:
    shape: Tuple[int, int]
    transform: Affine

    crs: CRS = attr.ib(
        metadata=dict(doc_exclude=True), default=None, hash=False, cmp=False
    )

    @classmethod
    def from_rio(cls, dataset: rasterio.DatasetReader) -> "GridSpec":
        return cls(shape=dataset.shape, transform=dataset.transform, crs=dataset.crs)

    @classmethod
    def from_h5(cls, dataset: h5py.Dataset) -> "GridSpec":
        return cls(
            shape=dataset.shape,
            transform=Affine.from_gdal(*dataset.attrs["geotransform"]),
            crs=CRS.from_wkt(dataset.attrs["crs_wkt"]),
        )


def generate_tiles(
    samples: int, lines: int, xtile: int = None, ytile: int = None
) -> Generator[Tuple[Tuple[int, int], Tuple[int, int]], None, None]:
    """
    Generates a list of tile indices for a 2D array.

    :param samples:
        An integer expressing the total number of samples in an array.

    :param lines:
        An integer expressing the total number of lines in an array.

    :param xtile:
        (Optional) The desired size of the tile in the x-direction.
        Default is all samples

    :param ytile:
        (Optional) The desired size of the tile in the y-direction.
        Default is min(100, lines) lines.

    :return:
        Each tuple in the generator contains
        ((ystart,yend),(xstart,xend)).

    >>> import pprint
    >>> tiles = generate_tiles(1624, 1567, xtile=1000, ytile=400)
    >>> pprint.pprint(list(tiles))
    [((0, 400), (0, 1000)),
     ((0, 400), (1000, 1624)),
     ((400, 800), (0, 1000)),
     ((400, 800), (1000, 1624)),
     ((800, 1200), (0, 1000)),
     ((800, 1200), (1000, 1624)),
     ((1200, 1567), (0, 1000)),
     ((1200, 1567), (1000, 1624))]
    """

    def create_tiles(samples, lines, xstart, ystart):
        """
        Creates a generator object for the tiles.
        """
        for ystep in ystart:
            if ystep + ytile < lines:
                yend = ystep + ytile
            else:
                yend = lines
            for xstep in xstart:
                if xstep + xtile < samples:
                    xend = xstep + xtile
                else:
                    xend = samples
                yield ((ystep, yend), (xstep, xend))

    # check for default or out of bounds
    if xtile is None or xtile < 0:
        xtile = samples
    if ytile is None or ytile < 0:
        ytile = min(100, lines)

    xstart = numpy.arange(0, samples, xtile)
    ystart = numpy.arange(0, lines, ytile)

    tiles = create_tiles(samples, lines, xstart, ystart)

    return tiles


class FileWrite:
    def __init__(self, gdal_options: Dict, gdal_config_options: Dict) -> None:
        super().__init__()

        self.options = gdal_options or {}
        self.config_options = gdal_config_options or {}

        self.default_levels = LEVELS

    @classmethod
    def from_existing(
        cls,
        shape: Tuple[float, float],
        overviews: bool = True,
        blockxsize: int = None,
        blockysize: int = None,
    ) -> "FileWrite":
        """ Returns write_img options according to the source imagery provided
        :param overviews:
            (boolean) sets overview flags in gdal config options
        :param blockxsize:
            (int) override the derived base blockxsize in cogtif conversion
        :param blockysize:
            (int) override the derived base blockysize in cogtif conversion

        returns a dict {'options': {}, 'config_options': {}}
        """
        # TODO Standardizing the Sentinel-2's overview tile size with external inputs
        options = {"compress": "deflate", "zlevel": 4}
        config_options = {}

        # Fallback to 512 value
        blockysize = blockysize or 512
        blockxsize = blockxsize or 512

        if shape[0] <= 512 and shape[1] <= 512:
            # Do not set block sizes for small imagery
            pass
        elif shape[1] <= 512:
            options["blockysize"] = min(blockysize, 512)
            # Set blockxsize to power of 2 rounded down
            options["blockxsize"] = int(2 ** (blockxsize.bit_length() - 1))
            # gdal does not like a x blocksize the same as the whole dataset
            if options["blockxsize"] == blockxsize:
                options["blockxsize"] = int(options["blockxsize"] / 2)
        else:
            if shape[1] == blockxsize:
                # dataset does not have an internal tiling layout
                # set the layout to a 512 block size
                blockxsize = 512
                blockysize = 512
                if overviews:
                    config_options["GDAL_TIFF_OVR_BLOCKSIZE"] = blockxsize

            options["blockxsize"] = blockxsize
            options["blockysize"] = blockysize
            options["tiled"] = "yes"

        if overviews:
            options["copy_src_overviews"] = "yes"

        return FileWrite(options, config_options)

    def write_from_ndarray(
        self,
        array: numpy.ndarray,
        out_filename: Path,
        geobox: GridSpec = None,
        nodata: int = None,
        overview_resampling=Resampling.nearest,
    ) -> None:
        """
        Writes a 2D/3D image to disk using rasterio.

        :param array:
            A 2D/3D NumPy array.

        :param out_filename:
            A string containing the output file name.

        :param geobox:
            An instance of a GriddedGeoBox object.

        :param nodata:
            A value representing the no data value for the array.

        :param overview_resampling:
            If levels is set, build overviews using a resampling method
            from `rasterio.enums.Resampling`
            Default is `Resampling.nearest`.

        :notes:
            If array is an instance of a `h5py.Dataset`, then the output
            file will include blocksizes based on the `h5py.Dataset's`
            chunks. To override the blocksizes, specify them using the
            `options` keyword. Eg {'blockxsize': 512, 'blockysize': 512}.
        """

        levels = self.default_levels

        # TODO: Old packager never passed in tags. Perhaps we want some?
        tags = {}

        dtype = array.dtype.name

        # Check for excluded datatypes
        excluded_dtypes = ["int64", "int8", "uint64"]
        if dtype in excluded_dtypes:
            raise TypeError("Datatype not supported: {dt}".format(dt=dtype))

        # convert any bools to uin8
        if dtype == "bool":
            array = np.uint8(array)
            dtype = "uint8"

        ndims = array.ndim
        dims = array.shape

        # Get the (z, y, x) dimensions (assuming BSQ interleave)
        if ndims == 2:
            samples = dims[1]
            lines = dims[0]
            bands = 1
        elif ndims == 3:
            samples = dims[2]
            lines = dims[1]
            bands = dims[0]
        else:
            raise IndexError(
                "Input array is not of 2 or 3 dimensions. Got {dims}".format(dims=ndims)
            )

        transform = None
        projection = None
        if geobox is not None:
            transform = geobox.transform
            projection = geobox.crs

        # compression predictor choices
        predictor = {
            "int8": 2,
            "uint8": 2,
            "int16": 2,
            "uint16": 2,
            "int32": 2,
            "uint32": 2,
            "int64": 2,
            "uint64": 2,
            "float32": 3,
            "float64": 3,
        }

        rio_args = {
            "count": bands,
            "width": samples,
            "height": lines,
            "crs": projection,
            "transform": transform,
            "dtype": dtype,
            "driver": "GTiff",
            "nodata": nodata,
            "predictor": predictor[dtype],
        }

        if isinstance(array, h5py.Dataset):
            # TODO: if array is 3D get x & y chunks
            if array.chunks[1] == array.shape[1]:
                # GDAL doesn't like tiled or blocksize options to be set
                # the same length as the columns (probably true for rows as well)
                array = array[:]
            else:
                y_tile, x_tile = array.chunks
                tiles = generate_tiles(samples, lines, x_tile, y_tile)

                if "tiled" in self.options:
                    rio_args["blockxsize"] = self.options.get("blockxsize", x_tile)
                    rio_args["blockysize"] = self.options.get("blockysize", y_tile)

        # the user can override any derived blocksizes by supplying `options`
        # handle case where no options are provided
        for key in self.options:
            rio_args[key] = self.options[key]

        def _rasterio_write_raster(out: Path):
            """
            This is a wrapper around rasterio writing tiles to
            enable writing to a temporary location before rearranging
            the overviews within the file by gdal when required
            """
            with rasterio.open(out, "w", **rio_args) as outds:
                if bands == 1:
                    if isinstance(array, h5py.Dataset):
                        for tile in tiles:
                            idx = (
                                slice(tile[0][0], tile[0][1]),
                                slice(tile[1][0], tile[1][1]),
                            )
                            outds.write(array[idx], 1, window=tile)
                    else:
                        outds.write(array, 1)
                else:
                    if isinstance(array, h5py.Dataset):
                        for tile in tiles:
                            idx = (
                                slice(tile[0][0], tile[0][1]),
                                slice(tile[1][0], tile[1][1]),
                            )
                            subs = array[:, idx[0], idx[1]]
                            for i in range(bands):
                                outds.write(subs[i], i + 1, window=tile)
                    else:
                        for i in range(bands):
                            outds.write(array[i], i + 1)
                if tags is not None:
                    outds.update_tags(**tags)

                # overviews/pyramids to disk
                if levels:
                    outds.build_overviews(levels, overview_resampling)

        if levels:
            # Write to temp directory first so we can add levels afterwards with gdal.
            with tempfile.TemporaryDirectory() as tmpdir:
                without_levels = Path(tmpdir) / out_filename.name
                _rasterio_write_raster(without_levels)
                # Creates the file at filename with the configured options
                # Will also move the overviews to the start of the file
                subprocess.check_call(
                    [
                        "gdal_translate",
                        "-co",
                        "{}={}".format("PREDICTOR", predictor[dtype]),
                        *self._gdal_cli_config,
                        without_levels,
                        out_filename,
                    ],
                    cwd=str(out_filename.parent),
                )
        else:
            # write directly to disk without rewriting with gdal
            _rasterio_write_raster(out_filename)

    @property
    def _gdal_cli_config(self):
        args = []
        for key, value in self.options.items():
            args.extend(["-co", "{}={}".format(key, value)])
        for key, value in self.config_options.items():
            args.extend(["--config", "{}".format(key), "{}".format(value)])
        return args

    def write_tif_from_h5(
        self,
        dataset: h5py.Dataset,
        out_fname: Path,
        nodata: int = None,
        geobox: GridSpec = None,
    ):
        """
        Method to write a h5 dataset or numpy array to a tif file
        :param dataset:
            h5 dataset containing a numpy array or numpy array
            Dataset will map to the raster data

        returns the out_fname param
        """
        if hasattr(dataset, "chunks"):
            data = dataset[:]
        else:
            data = dataset

        if nodata is None and hasattr(dataset, "attrs"):
            nodata = dataset.attrs.get("no_data_value")
        if geobox is None:
            geobox = GridSpec.from_h5(dataset)

        out_fname.parent.mkdir(exist_ok=True)

        self.write_from_ndarray(
            data,
            out_fname,
            nodata=nodata,
            geobox=geobox,
            overview_resampling=Resampling.average,
        )

    def write_from_file(
        self, input_image: Path, out_fname: Path, overviews: bool = True
    ) -> Path:
        """
        Compatible interface for writing (cog)tifs from a source file
        :param input_image:
            path to the source file

        :param out_fname:
            destination of the tif

        :param overviews:
            boolean flag to create overviews
            default (True)

        returns the out_fname param
        """

        with tempfile.TemporaryDirectory(
            dir=out_fname.parent, prefix="cogtif-"
        ) as tmpdir:
            # TODO: this modifies the input file? Probably need to make that clear
            run_command(["gdaladdo", "-clean", input_image], tmpdir)
            if overviews:
                run_command(
                    ["gdaladdo", "-r", "mode", input_image, *[str(l) for l in LEVELS]],
                    tmpdir,
                )

            run_command(
                [
                    "gdal_translate",
                    "-of",
                    "GTiff",
                    *self._gdal_cli_config,
                    input_image,
                    out_fname,
                ],
                input_image.parent,
            )

        return out_fname
