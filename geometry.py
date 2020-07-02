# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi, Ruggero Poletto"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

import math


# Get verts, faces, landuses


def get_geometry(feedback, layer, utm_origin):
    """!
    Get verts, faces, and landuses from sampling point layer.
    @param layer: QGIS vector layer of quad faces center points with landuse.
    @param utm_origin: domain origin in UTM CRS.
    @return verts, faces, landuses
    """
    feedback.setCurrentStep(8)
    feedback.pushInfo("Geometry: building the point matrix...")
    matrix = _get_matrix(layer=layer, utm_origin=utm_origin)
    if feedback.isCanceled():
        return {}
    feedback.setCurrentStep(9)
    feedback.pushInfo("Geometry: getting quad faces...")
    faces, landuses = _get_faces(matrix=matrix)
    if feedback.isCanceled():
        return {}
    feedback.setCurrentStep(10)
    feedback.pushInfo("Geometry: getting verts...")
    landuses_set = set(landuses)
    verts = _get_verts(matrix=matrix)
    feedback.setCurrentStep(11)
    return verts, faces, landuses, landuses_set


# Prepare the matrix of quad faces center points with landuse

# The layer is a flat list of quad faces center points (z, x, y, landuse)
# ordered by column. The original flat list is cut in columns, when three consecutive points
# form an angle < 180°.
# The returned matrix is a topological 2D representation of them by row (transposed).

# Same column:  following column:
#      first ·            first · · current
#            |                  | ^
#            |                  | |
#       prev ·                  | |
#            |                  |/
#    current ·             prev ·


# matrix:    j
#      o   o   o   o   o
#        ·   ·   ·   ·
#      o   *---*   o   o
# row    · | · | ·   ·   i
#      o   *---*   o   o
#        ·   ·   ·   ·
#      o   o   o   o   o
#
# · center points of quad faces
# o verts


def _norm(vector):
    return math.sqrt(vector[0] ** 2 + vector[1] ** 2)


def _dot_product(p0, p1, p2):
    v0 = [p1[0] - p0[0], p1[1] - p0[1]]
    v1 = [p2[0] - p0[0], p2[1] - p0[1]]
    return (v0[0] * v1[0] + v0[1] * v1[1]) / (_norm(v0) * _norm(v1))


def _get_matrix(layer, utm_origin):
    """
    Return the matrix of quad faces center points with landuse.
    @param layer: QGIS vector layer of quad faces center points with landuse.
    @param utm_origin: domain origin in UTM CRS.
    @return matrix of quad faces center points with landuse.
    """

    features = layer.getFeatures()  # get the points
    # Find matrix column length
    first_point, second_point = None, None
    ox, oy = utm_origin.x(), utm_origin.y()
    for f in features:
        g = f.geometry().get()  # QgsPoint
        point = (
            g.x() - ox,  # x, relative to origin
            g.y() - oy,  # y, relative to origin
        )
        if first_point is None:
            column_len, first_point = 1, point
        elif second_point is None:
            column_len, second_point = 2, point
        elif abs(_dot_product(first_point, second_point, point)) > 0.1:
            column_len += 1  # point on the same column
        else:
            break  # end of column
    # Prepare matrix by splitting features
    i, m = 0, []
    for f in features:
        g, a = f.geometry().get(), f.attributes()  # QgsPoint, landuse
        point = (
            g.x() - ox,  # x, relative to origin
            g.y() - oy,  # y, relative to origin
            g.z(),  # z absolute
            a[5] or 0,  # landuse, protect from None
        )
        i += 1
        if i == 1:  # first point of the m column
            m.append(
                [point,]
            )
        elif i == column_len:  # last point
            i = 0
        else:  # following point
            m[-1].append(point)
    return list(map(list, zip(*m)))  # transpose


# Getting face connectivity and landuse

#        j   j  j+1
#        *<------* i
#        | f1 // |
# faces  |  /·/  | i
#        | // f2 |
#        *------>* i+1


def _get_vert_index(i, j, len_vrow):
    # F90 indexes start from 1, so +1
    return i * len_vrow + j + 1


def _get_f1(i, j, len_vrow):
    return (
        _get_vert_index(i, j, len_vrow),
        _get_vert_index(i + 1, j, len_vrow),
        _get_vert_index(i, j + 1, len_vrow),
    )


def _get_f2(i, j, len_vrow):
    return (
        _get_vert_index(i + 1, j + 1, len_vrow),
        _get_vert_index(i, j + 1, len_vrow),
        _get_vert_index(i + 1, j, len_vrow),
    )


def _get_faces(matrix):
    """
    Get face connectivity and landuses.
    @param matrix: matrix of quad faces center points with landuse.
    @return faces and landuses
    """
    faces, landuses = list(), list()
    len_vrow = len(matrix[0]) + 1
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            faces.extend((_get_f1(i, j, len_vrow), _get_f2(i, j, len_vrow)))
            landuses.extend((p[3], p[3]))
    return faces, landuses


# Getting vertices

# First inject ghost centers all around the vertices
# then extract the vertices by averaging the neighbour centers coordinates

# · centers of quad faces  + ghost centers
# o verts  * cs  x vert
#
#           dx     j  j+1
#          + > +   +   +   +   +
#       dy v o   o   o   o   o
#          +   *   *   ·   ·   +
#            o   x   o   o   o
# pres_row +   *   *   ·   ·   +  i-1
#            o   o---o   o   o
#      row +   · | · | ·   ·   +  i
#            o   o---o   o   o
#          +   +   +   +   +   +

#              j      j+1
# prev_row     *       * i-1
#
#          o-------x
#          |       |
#      row |   *   |   * i
#          |       |
#          o-------o


def _inject_ghost_centers(matrix):
    """
    Inject ghost centers into the matrix.
    """

    # Calc displacements for ghost centers
    fsub = lambda a: a[0] - a[1]
    fadd = lambda a: a[0] + a[1]
    dx = list(map(fsub, zip(matrix[0][1], matrix[0][0])))
    dy = list(map(fsub, zip(matrix[1][0], matrix[0][0])))
    # no vertical displacement for ghost centers (smoother)
    dx[2], dy[2] = 0.0, 0.0

    # Insert new first ghost row
    row = list(tuple(map(fsub, zip(c, dy))) for c in matrix[0])
    matrix.insert(0, row)

    # Append new last ghost row
    row = list(tuple(map(fadd, zip(c, dy))) for c in matrix[-1])
    matrix.append(row)

    # Insert new first and last ghost col
    for row in matrix:
        # new first ghost col
        gc = tuple(map(fsub, zip(row[0], dx)))
        row.insert(0, gc)
        # new last ghost col
        gc = tuple(map(fadd, zip(row[-1], dx)))
        row.append(gc)


def _get_neighbour_centers(prev_row, row, j):
    return (
        prev_row[j][:-1],  # rm landuse from center (its last value)
        prev_row[j + 1][:-1],
        row[j][:-1],
        row[j + 1][:-1],
    )


def _avg(l):
    return sum(l) / len(l)


def _get_vert(neighbour_centers):
    return tuple(map(_avg, zip(*neighbour_centers)))  # avg of centers coordinates


def _get_verts(matrix):
    """
    Get vertices from the center matrix.
    @param matrix: matrix of quad faces center points with landuse.
    @return verts
    """
    _inject_ghost_centers(matrix)  # modification in place
    verts = list()
    prev_row = matrix[0]
    for row in matrix[1:]:  # matrix[0] is prev_row
        for j, _ in enumerate(row[:-1]):
            verts.append(_get_vert(_get_neighbour_centers(prev_row, row, j)))
        prev_row = row
    return verts
