import bpy
from bpy.types import Operator
from bpy.props import EnumProperty


class OBJECT_OT_pt_origin_set(Operator):
    bl_idname = 'object.pt_origin_set'
    bl_label = 'Set Pivot' # /Cursor
    bl_description = 'Set the origin using the selected mode'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    type: EnumProperty(
        name = 'Type',
        items = [
            ('ORIGIN_CENTER_OF_VOLUME', 'Origin to Center of Mass (Volume)', 'Calculate the center of mass from the volume (must be manifold geometry with consistent normals)', '', 0),
            ('ORIGIN_CENTER_OF_MASS', 'Origin to Center of Mass (Surface)', 'Calculate the center of mass from the surface area', '', 1),
            ('ORIGIN_CURSOR', 'Origin to 3D Cursor', 'Move the object origin to the 3D cursor', '', 2),
            ('ORIGIN_GEOMETRY', 'Origin to Geometry', 'Move the object origin to the geometry center', '', 3),
            ('GEOMETRY_ORIGIN', 'Geometry to Origin', 'Move object geometry to the current origin', '', 4),
            ],
        default = 'ORIGIN_CENTER_OF_MASS',
        )

    center: EnumProperty(
        name = 'Center',
        items = [
            ('MEDIAN', 'Median Center', 'Use the median point', '', 0),
            ('BOUNDS', 'Bounds Center', 'Use the bounding-box center', '', 1),
            ],
        default = 'MEDIAN',
        )

    @classmethod
    def poll(cls, context):
        return context.active_object

    @classmethod
    def description(self, context, properties):
        if properties.type == 'ORIGIN_CENTER_OF_VOLUME':
            return 'Calculate the center of mass from the volume (must be manifold geometry with consistent normals)'
        elif properties.type == 'ORIGIN_CENTER_OF_MASS':
            return 'Calculate the center of mass from the surface area'
        elif properties.type == 'ORIGIN_CURSOR':
            return 'Move the object origin to the 3D cursor'
        elif properties.type == 'ORIGIN_GEOMETRY':
            return 'Move the object origin to the geometry center'
        elif properties.type == 'GEOMETRY_ORIGIN':
            return 'Move object geometry to the current origin'
        return self.bl_description

    def execute(self, context):
        bpy.ops.object.origin_set(type=self.type, center=self.center)
        return {'FINISHED'}


classes = [
    OBJECT_OT_pt_origin_set,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
