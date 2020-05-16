# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi, Ruggero Poletto"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

from qgis.core import QgsProcessingException, QgsMapSettings, QgsMapRendererParallelJob
from qgis.utils import iface
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import QSize


# Write to file


def write_file(filepath, content):
    """
    Write a text to filepath.
    """
    try:
        with open(filepath, "w") as f:
            f.write(content)
    except IOError:
        raise QgsProcessingException(f"File not writable at <{filepath}>")


def write_image(destination_crs, extent, filepath, imagetype):
    """
    Save current QGIS canvas to image file.
    """
    settings = QgsMapSettings()  # build settings
    settings.setDestinationCrs(destination_crs)  # set output crs
    settings.setExtent(extent)  # in destination_crs
    layers = iface.mapCanvas().layers()  # get visible layers
    settings.setLayers(layers)

    w = 1920 * 2  # TODO improve!
    h = int(
        (extent.yMaximum() - extent.yMinimum())
        / (extent.xMaximum() - extent.xMinimum())
        * w
    )
    settings.setOutputSize(QSize(w, h))
    settings.setOutputDpi(200)

    render = QgsMapRendererParallelJob(settings)
    render.start()
    render.waitForFinished()
    image = render.renderedImage()
    try:
        image.save(filepath, imagetype)
    except IOError:
        raise QgsProcessingException(f"Image not writable at <{filepath}>")


# Geographic operations


def get_utm_str(utm_point, utm_crs):  # FIXME not used anymore
    return f"{utm_point.x()}m E {utm_point.y()}m N ({utm_crs.description()})"


def get_lonlat_url(wgs84_point):
    return f"http://www.openstreetmap.org/?mlat={wgs84_point.y()}&mlon={wgs84_point.x()}&zoom=12"


def lonlat_to_zn(lon, lat):
    """!
    Conversion from longitude/latitude to UTM zone number.
    @param lon: longitude in decimal degrees.
    @param lat: latitude in decimal degrees.
    @return the UTM zone number.
    """
    if 56 <= lat < 64 and 3 <= lon < 12:
        return 32
    if 72 <= lat <= 84 and lon >= 0:
        if lon < 9:
            return 31
        elif lon < 21:
            return 33
        elif lon < 33:
            return 35
        elif lon < 42:
            return 37
    return int((lon + 180) / 6) + 1


def lat_to_ne(lat):
    """!
    Detect if latitude is on the UTM north hemisphere.
    @param lat: latitude in decimal degrees.
    @return True if UTM north hemisphere. False otherwise.
    """
    if lat >= -1e-6:
        return True
    else:
        return False


def lonlat_to_epsg(lon, lat):
    """!
    Conversion from longitude/latitude to EPSG.
    @param lon: longitude in decimal degrees.
    @param lat: latitude in decimal degrees.
    @return the EPSG.
    """
    zn = lonlat_to_zn(lon=lon, lat=lat)
    if lat_to_ne(lat):
        return "EPSG:326" + str(zn).zfill(2)
    else:
        return "EPSG:327" + str(zn).zfill(2)
