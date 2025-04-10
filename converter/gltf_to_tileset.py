import json
import numpy as np
import math
from gltf.gltf import Axis, Gltf
from tileset import Tile, Tileset, Measure
from pathlib import Path
from gltf import Slicer, io
from utils import Box3, Matrix4


def build_bvh(tiles):
    split = -1
    min_cost = math.inf
    split_axis = -1

    if len(tiles) < 3:
        return Tile().add_children(tiles)

    for axis in range(3):
        sorted_tiles = sorted(
            tiles, key=lambda tile: tile.centroid_world[axis])
        left_box = Box3()
        right_box = Box3()
        left_cost = [0] * (len(sorted_tiles) - 1)
        right_cost = [0] * (len(sorted_tiles) - 1)
        for i in range(len(sorted_tiles)-1):
            left_box.union(sorted_tiles[i].box_world)
            right_box.union(sorted_tiles[-i-1].box_world)
            left_cost[i] = sah_cost(left_box.size, i + 1)
            right_cost[-i-1] = sah_cost(right_box.size, i + 1)
        costs = list(
            map(lambda l, r: l + r, left_cost, right_cost))
        min_cost_axis = min(costs)
        if min_cost_axis < min_cost:
            min_cost = min_cost_axis
            split = np.argmin(costs) + 1
            split_axis = axis

    sorted_tiles = sorted(
        tiles, key=lambda tile: tile.centroid_world[split_axis])
    return Tile().add_child(build_bvh(sorted_tiles[:split])).add_child(build_bvh(sorted_tiles[split:]))


def sah_cost(size, count):
    return (size[0] * size[1] + size[1] * size[2] + size[2] * size[0]) * count


def split_group(source):
    tiles = source[:]
    length = len(tiles)
    if 1 == length:
        return [tiles[0]]

    if 2 == length:
        return [Tile().add_child(tiles.pop()).add_child(tiles.pop())]

    groups = []
    while tiles:
        box = tiles[-1].box_world
        group = []
        rest = []
        for tile in tiles:
            if box.contains(tile.box_world):
                group.append(tile)
            else:
                rest.append(tile)
        # group = list(filter(lambda tile: box.contains(tile.box_world), tiles))
        tile = Tile().add_child(group.pop())
        if group:
            tile.add_children(split_group(group))

        groups.append(tile)
        tiles = rest

    return groups


def gltf_to_tileset(fin, fout, measure: Measure = Measure.METER, up_direction: Axis = Axis.Y):
    Gltf.up_direction = up_direction
    gltf, buffers = io.read_gltf(fin)
    Path(fout).parent.mkdir(parents=True, exist_ok=True)
    gltf_slicer = Slicer(gltf, buffers=buffers)
    Tile.measure = measure
    tiles = list(map(
        lambda id: Tile(
            content_id=id,
            instance_box=gltf_slicer.get_bounding_box(id),
            instances_matrices=gltf_slicer.get_matrices(id),
            matrix=Matrix4(),
            gltf=gltf_slicer.slice_mesh(id).as_bytes(),
            extras=gltf_slicer.get_extras(id)
        ),
        range(gltf_slicer.meshes_count)
    ))
    print('meshes count:', gltf_slicer.meshes_count)

    # 生成 tileset.json
    tiles.sort(key=lambda tile: tile.box_world.diagonal) # 按对角线长度排序
    grouped_tiles = split_group(tiles)
    root = build_bvh(grouped_tiles)
    root.refine = "ADD"
    tileset = Tileset(root)
    with open(fout, "w") as f:
        json.dump(tileset.dict, f, separators=(",", ":"))

    for tile in tiles:
        with open(Path(fout).parent / tile.content.uri, "wb") as f:
            f.write(tile.content.as_bytes())

    io.copy_textures(fin, fout, gltf.images)
