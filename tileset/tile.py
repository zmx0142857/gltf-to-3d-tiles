from .b3dm import B3dm
from .i3dm import I3dm
from functools import cached_property
from utils import Box3, Matrix4
from enum import Enum
from gltf import Gltf, Axis

FOOT_TO_METER_MULTIPLIER = 0.3048
MILLIMETER_TO_METER_MULTIPLIER = 0.001

class Measure(str, Enum):
    METER = "meter"
    FOOT = "foot"
    MILLIMETER = "millimeter"


class Tile:
    measure = Measure.METER

    def __init__(self, *, content_id=None, refine=None, matrix=Matrix4(), box=Box3(), instance_box=Box3(), instances_matrices=None, gltf=None, extras=None) -> None:
        self.refine = refine
        self.__content_id = content_id
        # self.__content = None
        self.__matrix = matrix.clone()
        self.__content_matrices = instances_matrices
        self.__instance_box = instance_box
        self.__box = box.clone()
        self.__children = []
        self.__gltf = gltf
        self.__extras = extras
        # self.__parse_children()

    def add_child(self, tile):
        if not tile:
            return self

        self.__children.append(tile)
        self.__box.union(tile.box_world)
        return self

    def add_children(self, children):
        if not children:
            return self

        for child in children:
            self.add_child(child)
        return self

    def add_content_matrix(self, matrix):
        self.__content_matrices.append(matrix)

    @property
    def content(self):
        if 1 < len(self.__content_matrices):
            return I3dm(str(self.__content_id),
                        self.__gltf, self.__content_matrices, extras=self.__extras)
        else:
            return B3dm(str(self.__content_id), self.__gltf, extras=self.__extras)

    @property
    def __content_matrix(self):
        if self.__content_matrices and 1 == len(self.__content_matrices):
            return self.__content_matrices[0]

        return Matrix4()

    @property
    def __content_box(self):
        if self.__content_matrices is not None and 1 < len(self.__content_matrices):
            box = Box3()
            for matrix in self.__content_matrices:
                box.union(
                    self.__instance_box.clone().apply_matrix4(matrix.matrix))
            return box

        return self.__instance_box

    @property
    def size(self):
        return self.box.size

    @property
    def centroid(self):
        return self.box.center

    @property
    def matrix(self):
        return self.__matrix.clone().multiply(self.__content_matrix)

    def apply_matrix4(self, matrix):
        self.__matrix.premultiply(matrix)
        return self

    @property
    def children(self):
        return self.__children

    @property
    def box(self):
        return self.__box if self.__content_id is None else self.__box.clone().union(self.__content_box)

    @cached_property
    def box_world(self):
        debug = self.__content_id == 2
        res = self.box.clone().apply_matrix4(self.matrix.matrix, debug)
        # if debug:
        #     print(2, self.box.list)
        #     print(2, self.__matrix.matrix)
        #     print(2, self.__content_matrix.matrix)
        #     print(2, self.matrix.matrix)
        #     print(2, res.list)
        return res

    @property
    def centroid_world(self):
        return self.box_world.center

    @property
    def geometric_error(self):
        if self.__content_id is None:
            return max(list(map(lambda tile: tile.geometric_error, self.__children)))

        if Tile.measure is Measure.FOOT:
            return self.__instance_box.diagonal * FOOT_TO_METER_MULTIPLIER
        elif Tile.measure is Measure.MILLIMETER:
            return self.__instance_box.diagonal * MILLIMETER_TO_METER_MULTIPLIER

        return self.__instance_box.diagonal

    @property
    def dict(self):
        ret = {
            "geometricError": self.geometric_error,
            "refine": self.refine
        }
        box = self.box.list
        if Gltf.up_direction is Axis.Z:
            tmp = box[2]
            box[2] = box[1]
            box[1] = box[0]
            box[0] = tmp
            if self.__content_id is None:
                tmp = box[11]
                box[11] = box[7]
                box[7] = box[3]
                box[3] = tmp
            else:
                tmp = box[3]
                box[3] = box[7]
                box[7] = box[11]
                box[11] = tmp
        ret["boundingVolume"] = {"box": box}

        if not self.matrix.is_identity:
            ret["transform"] = self.matrix.list
            if Gltf.up_direction is Axis.Z:
                t = ret["transform"]
                ret["transform"] = [
                    t[9], t[8], t[10], t[11],
                    t[5], t[4], t[6], t[7],
                    t[1], t[0], t[2], t[3],
                    t[14], t[12], t[13], t[15]
                ]

        if self.__content_id is not None:
            ret["content"] = self.content.dict

        if self.children:
            ret["children"] = [
                child.dict for child in self.children]

        return {k: v for k, v in ret.items() if v is not None}
