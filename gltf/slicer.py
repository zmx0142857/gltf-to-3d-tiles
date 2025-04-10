from .gltf import Glb
import utils
from .element import Element
import sys


def get__attribute(obj, name):
    ret = []
    for key, value in obj.__dict__.items():
        if key == name:
            ret.append(value)
        elif type(value) == Element:
            ret += get__attribute(value, name)

    return ret


def set__texture(material, name, texture_indices):
    for key, value in material.__dict__.items():
        if key == name:
            setattr(material, key, texture_indices.index(value))
        elif type(value) == Element:
            set__texture(value, name, texture_indices)


class Slicer(Element):
    def __init__(self, gltf, **kwargs):

        super().__init__(gltf, **kwargs)
        self.__matrices = [[] for _ in range(len(self.meshes))]
        self.__extras = [[] for _ in range(len(self.meshes))]
        scene = 0 if self.scene is None else self.scene
        for root in self.scenes[scene].nodes:
            # root = self.scenes[scene].nodes[0]
            self.__parse_node(root)
        if not self.images:
            return

        for image in self.images:
            if not image.uri:
                continue

            image.uri = image.uri.replace("\\", "/")

    def __parse_node(self, node_index, *, matrix=utils.Matrix4(), extras=None):
        node = self.nodes[node_index]

        if node.matrix:
            matrix = matrix.clone().multiply(utils.Matrix4(node.matrix))
            if node.scale:
                print('warning: check for scale', node)
            if node.rotation:
                print('warning: check for rotation', node)
            if node.translation:
                print('warning: check for translation', node)
            # TODO Check for translation/scale/rotation here?
        else:
            if node.scale:
                matrix = matrix.clone().scaleBy(node.scale)
            if node.rotation:
                matrix = matrix.clone().rotateBy(node.rotation)
            if node.translation:
                matrix = matrix.clone().translateBy(node.translation)

        if node.extras:
            extras = node.extras

        if node.mesh is not None:
            self.__matrices[node.mesh].append(matrix)
            if extras is not None:
                self.__extras[node.mesh].append(extras.as_dict())

        if node.children:
            for index in node.children:
                self.__parse_node(index, matrix=matrix, extras=extras)

    def get_matrices(self, mesh_id):
        return self.__matrices[mesh_id]

    def get_extras(self, mesh_id):
        return self.__extras[mesh_id]

    @property
    def meshes_count(self):
        return len(self.meshes)

    def slice_primitives(self, primitives: list):
        accessor_indices = self.__get_accessor_indices(primitives)
        material_indices = self.__get_material_indices(primitives)
        texture_indices = self.__get_texture_indices(material_indices)
        sampler_indices = self.__get_sampler_indices(texture_indices)
        image_indices = self.__get_image_indices(texture_indices)
        buffer_view_indices = list(set([
            self.accessors[id].buffer_view for id in accessor_indices] + [
            self.images[id].buffer_view for id in image_indices if self.images[id].buffer_view is not None]))
        return Glb([self.__get_buffer(buffer_view_indices)],
            meshes=self.__get_meshes(primitives, accessor_indices, material_indices),
            accessors=self.__get_accessors(accessor_indices, buffer_view_indices),
            buffer_views=self.__get_buffer_views(buffer_view_indices),
            materials=self.__get_materials(material_indices, image_indices),
            textures=self.__get_textures(len(texture_indices)),
            images=self.__get_images(image_indices, buffer_view_indices),
            samplers=self.__get_samplers(len(sampler_indices))
        )

    def __get_images(self, image_indices, buffer_view_indices):
        ret = [self.images[id].clone() for id in image_indices]
        for image in ret:
            if image.buffer_view:
                image.buffer_view = buffer_view_indices.index(
                    image.buffer_view)

        return ret

    def __get_textures(self, count):
        if self.textures:
            return self.textures[:count]

    def __get_samplers(self, count):
        if self.samplers:
            return self.samplers[:count]

    def __get_texture_indices(self, material_indices):
        ret = []
        for id in material_indices:
            ret += get__attribute(self.materials[id], "index")

        return ret
        # return [self.materials[id].pbr_metallic_roughness.base_color_texture.index for id in material_indices if
        #         self.materials[id].pbr_metallic_roughness.base_color_texture is not None]

    def __get_image_indices(self, texture_indices):
        return [self.textures[id].source for id in texture_indices]

    def __get_sampler_indices(self, texture_indices):
        return [self.textures[id].sampler for id in texture_indices if self.textures[id].sampler is not None]

    def slice_mesh(self, mesh_id: int):
        return self.slice_primitives(self.meshes[mesh_id].primitives)

    def __get_accessor_indices(self, primitives):
        ret = set()
        for p in primitives:
            ret.add(p.indices)
            ret.update(set(p.attributes.__dict__.values()))

        return list(ret)

    def __get_material_indices(self, primitives):
        return [primitive.material for primitive in primitives if primitive.material is not None]

    def __get_materials(self, material_indices, texture_indices):
        materials = [self.materials[id].clone()
                     for id in material_indices]

        for material in materials:
            set__texture(material, "index", texture_indices)
            # if material.pbr_metallic_roughness.base_color_texture is not None:
            #     material.pbr_metallic_roughness.base_color_texture.index = texture_indices.index(
            #         material.pbr_metallic_roughness.base_color_texture.index)
        return materials

    def __get_buffer(self, buffer_view_indices):
        ret = bytearray()
        for index in buffer_view_indices:
            view = self.buffer_views[index]
            byte_offset = view.byte_offset if view.byte_offset else 0
            padding = utils.padded_len(view.byte_length) - view.byte_length;
            ret += self.buffers[view.buffer][byte_offset:byte_offset + view.byte_length]
            ret += b'\0' * padding
        return ret

    def __get_buffer_views(self, buffer_view_indices):
        ret = [self.buffer_views[index].clone()
               for index in buffer_view_indices]
        offset = 0
        for view in ret:
            view.buffer = 0
            view.byte_offset = offset
            offset += utils.padded_len(view.byte_length)

        return ret

    def __get_accessors(self, accessor_indices, buffer_view_indices):
        ret = [self.accessors[index].clone() for index in accessor_indices]
        for accessor in ret:
            accessor.buffer_view = buffer_view_indices.index(
                accessor.buffer_view)
        return ret

    def get_bounding_box_by_primitives(self, primitives: list):
        box = utils.Box3()
        for primitive in primitives:
            accessor = self.accessors[primitive.attributes.POSITION]
            box.expand_by_point(accessor.max).expand_by_point(accessor.min)

        return box

    def get_bounding_box(self, mesh_id: int):
        return self.get_bounding_box_by_primitives(self.meshes[mesh_id].primitives)

    def __get_meshes(self, primitives, accessor_indices, material_indices):
        ret = []
        for p in primitives:
            indices = accessor_indices.index(p.indices)
            attributes = {k: accessor_indices.index(v)
                          for k, v in p.attributes.__dict__.items()}
            material = None
            if p.material is not None:
                material = material_indices.index(p.material)
            ret.append(Element(indices=indices,
                       attributes=attributes, material=material))
        return [Element(primitives=ret)]
