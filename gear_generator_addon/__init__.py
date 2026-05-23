bl_info = {
    "name": "齿轮生成器 5.1",
    "author": "GitHub Copilot",
    "version": (1, 0, 0),
    "blender": (5, 1, 0),
    "location": "视图 3D > 侧边栏 > 齿轮生成器",
    "description": "生成参数化外齿轮、内齿轮、齿形、齿条、平行轴、交错轴、倾斜轴和啮合齿轮。",
    "warning": "Blender 5.1 实验性齿轮生成插件。",
    "category": "网格",
}

import bpy
import bmesh
from math import cos, sin, pi, radians
from mathutils import Vector, Matrix


class GearGeneratorProperties(bpy.types.PropertyGroup):
    num_teeth: bpy.props.IntProperty(
        name="齿数",
        description="齿轮的齿数",
        default=24,
        min=4,
        max=128,
    )
    module: bpy.props.FloatProperty(
        name="模数",
        description="控制齿轮整体尺寸的模数",
        default=1.0,
        min=0.05,
        max=10.0,
    )
    thickness: bpy.props.FloatProperty(
        name="厚度",
        description="齿轮主体的厚度",
        default=0.4,
        min=0.05,
        max=5.0,
    )
    pressure_angle: bpy.props.FloatProperty(
        name="压力角",
        description="用于齿形的压力角",
        default=20.0,
        min=10.0,
        max=30.0,
    )
    helix_angle: bpy.props.FloatProperty(
        name="螺旋角",
        description="斜齿或人字齿的螺旋角",
        default=15.0,
        min=0.0,
        max=45.0,
    )
    tooth_type: bpy.props.EnumProperty(
        name="齿型",
        description="选择齿轮齿型",
        items=[
            ('SPUR', "直齿", "直线齿轮"),
            ('HELICAL', "斜齿", "倾斜螺旋形齿轮"),
            ('HERRINGBONE', "人字齿", "镜像斜齿齿轮"),
        ],
        default='SPUR',
    )
    gear_type: bpy.props.EnumProperty(
        name="齿轮类型",
        description="选择齿轮类型或配对形式",
        items=[
            ('EXTERNAL', "外齿轮", "标准外齿轮"),
            ('INTERNAL', "内齿轮", "带内齿的环形齿轮"),
            ('INVOLUTE', "齿形齿轮", "近似渐开线齿形的外齿轮"),
            ('RACK', "齿条", "线性齿条"),
            ('PARALLEL', "平行轴", "平行轴齿轮对"),
            ('INTERSECTING', "交错轴", "交错轴锥齿轮对"),
            ('SKEW', "倾斜轴", "倾斜轴齿轮对"),
            ('MESHING', "内外啮合", "内齿轮与外齿轮啮合"),
        ],
        default='EXTERNAL',
    )
    addendum: bpy.props.FloatProperty(
        name="Addendum",
        description="Addendum height for gear teeth",
        default=1.0,
        min=0.1,
        max=5.0,
    )
    dedendum: bpy.props.FloatProperty(
        name="Dedendum",
        description="Dedendum depth for gear teeth",
        default=1.25,
        min=0.1,
        max=5.0,
    )


def make_gear_profile(num_teeth, pitch_radius, addendum, dedendum, pressure_angle, internal=False, involute=False):
    tooth_angle = 2.0 * pi / num_teeth
    base_radius = pitch_radius * cos(radians(pressure_angle))
    sign = -1.0 if internal else 1.0
    outer_radius = pitch_radius + sign * addendum
    root_radius = pitch_radius - sign * dedendum
    root_angle = tooth_angle * 0.45
    tip_angle = tooth_angle * 0.16
    vertices = []

    for tooth_index in range(num_teeth):
        center = tooth_index * tooth_angle
        root_left = center - root_angle
        tip_left = center - tip_angle
        tip_right = center + tip_angle
        root_right = center + root_angle

        if involute and not internal:
            segments = 3
            for i in range(segments + 1):
                alpha = root_left + (tip_left - root_left) * i / segments
                r = root_radius + (outer_radius - root_radius) * (i / segments)**1.2
                vertices.append((r * cos(alpha), r * sin(alpha)))
        else:
            vertices.append((root_radius * cos(root_left), root_radius * sin(root_left)))

        vertices.append((outer_radius * cos(tip_left), outer_radius * sin(tip_left)))
        vertices.append((outer_radius * cos(tip_right), outer_radius * sin(tip_right)))
        vertices.append((root_radius * cos(root_right), root_radius * sin(root_right)))

    return vertices


def build_gear_mesh(name, props, offset_matrix=Matrix.Identity(4), override_gear_type=None):
    gear_type = override_gear_type if override_gear_type is not None else props.gear_type
    num_teeth = props.num_teeth
    module = props.module
    pitch_radius = module * num_teeth * 0.5
    addendum = props.addendum * module
    dedendum = props.dedendum * module
    involute = gear_type == 'INVOLUTE'
    internal = gear_type == 'INTERNAL'
    thickness = props.thickness
    tooth_type = props.tooth_type

    if gear_type == 'RACK':
        return build_rack_mesh(name, num_teeth, module, thickness, props)

    profile = make_gear_profile(num_teeth, pitch_radius, addendum, dedendum, props.pressure_angle, internal=internal, involute=involute)
    bm = bmesh.new()
    top_verts = []
    bottom_verts = []
    for x, y in profile:
        bottom_verts.append(bm.verts.new((x, y, -thickness * 0.5)))
        top_verts.append(bm.verts.new((x, y, thickness * 0.5)))

    bm.verts.ensure_lookup_table()
    num_loop = len(profile)
    for i in range(num_loop):
        v0 = bottom_verts[i]
        v1 = bottom_verts[(i + 1) % num_loop]
        v2 = top_verts[(i + 1) % num_loop]
        v3 = top_verts[i]
        bm.faces.new((v0, v1, v2, v3))

    bm.faces.new(top_verts)
    bm.faces.new(reversed(bottom_verts))

    if tooth_type != 'SPUR' and props.gear_type != 'RACK':
        twist_angle = radians(props.helix_angle)
        for v in bm.verts:
            z_norm = (v.co.z + thickness * 0.5) / thickness
            twist = twist_angle * (z_norm - 0.5)
            if tooth_type == 'HERRINGBONE':
                if v.co.z > 0:
                    twist = twist_angle * z_norm
                else:
                    twist = -twist_angle * (1.0 - z_norm)
            if twist != 0.0:
                v.co.xy = Vector((v.co.x, v.co.y)).rotated(twist)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    obj.matrix_world = offset_matrix
    bpy.context.collection.objects.link(obj)
    return obj


def build_rack_mesh(name, num_teeth, module, thickness, props):
    tooth_width = module * 0.7
    tooth_height = props.addendum * module
    length = num_teeth * tooth_width * 1.2
    width = module * 1.5
    bm = bmesh.new()
    verts = []
    for x in [0.0, length]:
        for y in [-width * 0.5, width * 0.5]:
            for z in [-thickness * 0.5, thickness * 0.5]:
                verts.append(bm.verts.new((x, y, z)))
    bm.faces.new((verts[0], verts[2], verts[3], verts[1]))
    bm.faces.new((verts[4], verts[5], verts[7], verts[6]))
    bm.faces.new((verts[0], verts[1], verts[5], verts[4]))
    bm.faces.new((verts[2], verts[6], verts[7], verts[3]))
    bm.faces.new((verts[1], verts[3], verts[7], verts[5]))
    bm.faces.new((verts[0], verts[4], verts[6], verts[2]))

    # add simple teeth along top edge
    for i in range(num_teeth):
        x_start = i * tooth_width * 1.2
        x_end = x_start + tooth_width
        y = width * 0.5
        tooth_verts = [
            bm.verts.new((x_start, y, -thickness * 0.5)),
            bm.verts.new((x_end, y, -thickness * 0.5)),
            bm.verts.new((x_end, y + tooth_height, -thickness * 0.5)),
            bm.verts.new((x_start, y + tooth_height, -thickness * 0.5)),
            bm.verts.new((x_start, y, thickness * 0.5)),
            bm.verts.new((x_end, y, thickness * 0.5)),
            bm.verts.new((x_end, y + tooth_height, thickness * 0.5)),
            bm.verts.new((x_start, y + tooth_height, thickness * 0.5)),
        ]
        bm.faces.new((tooth_verts[0], tooth_verts[1], tooth_verts[2], tooth_verts[3]))
        bm.faces.new((tooth_verts[4], tooth_verts[7], tooth_verts[6], tooth_verts[5]))
        bm.faces.new((tooth_verts[0], tooth_verts[4], tooth_verts[5], tooth_verts[1]))
        bm.faces.new((tooth_verts[1], tooth_verts[5], tooth_verts[6], tooth_verts[2]))
        bm.faces.new((tooth_verts[2], tooth_verts[6], tooth_verts[7], tooth_verts[3]))
        bm.faces.new((tooth_verts[3], tooth_verts[7], tooth_verts[4], tooth_verts[0]))

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def create_gear_pair(props):
    main_obj = build_gear_mesh("Gear_Main", props)
    if props.gear_type == 'PARALLEL':
        partner = build_gear_mesh("Gear_Parallel", props, Matrix.Translation((props.module * props.num_teeth * 1.2, 0, 0)))
        partner.rotation_euler = (0.0, 0.0, pi)
        return [main_obj, partner]
    if props.gear_type == 'INTERSECTING':
        partner = build_gear_mesh("Gear_Intersecting", props)
        partner.matrix_world = Matrix.Translation((props.module * props.num_teeth * 0.9, 0, 0)) @ Matrix.Rotation(radians(90.0), 4, 'Y')
        return [main_obj, partner]
    if props.gear_type == 'SKEW':
        partner = build_gear_mesh("Gear_Skew", props)
        partner.matrix_world = Matrix.Translation((props.module * props.num_teeth * 0.8, 0, 0)) @ Matrix.Rotation(radians(45.0), 4, 'Y')
        return [main_obj, partner]
    if props.gear_type == 'MESHING':
        partner = build_gear_mesh("Gear_Meshing_Internal", props, Matrix.Identity(4), override_gear_type='INTERNAL')
        partner.location = Vector((0, 0, 0))
        main_obj.location = Vector((0, 0, 0))
        return [main_obj, partner]
    return [main_obj]


class OBJECT_OT_generate_gear(bpy.types.Operator):
    bl_idname = "mesh.generate_gear"
    bl_label = "生成齿轮"
    bl_description = "使用当前设置创建新齿轮网格"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.gear_generator_props
        created = []

        if props.gear_type in {'PARALLEL', 'INTERSECTING', 'SKEW', 'MESHING'}:
            created = create_gear_pair(props)
        else:
            created = [build_gear_mesh("Gear", props)]

        for obj in created:
            obj.select_set(True)
        context.view_layer.objects.active = created[-1]

        self.report({'INFO'}, f"Created {len(created)} gear object(s)")
        return {'FINISHED'}


class VIEW3D_PT_gear_generator_panel(bpy.types.Panel):
    bl_label = "齿轮生成器"
    bl_idname = "VIEW3D_PT_gear_generator_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '齿轮生成器'

    def draw(self, context):
        layout = self.layout
        props = context.scene.gear_generator_props

        layout.prop(props, "gear_type")
        layout.prop(props, "tooth_type")
        layout.prop(props, "num_teeth")
        layout.prop(props, "module")
        layout.prop(props, "thickness")
        layout.prop(props, "pressure_angle")
        if props.tooth_type != 'SPUR':
            layout.prop(props, "helix_angle")
        layout.prop(props, "addendum")
        layout.prop(props, "dedendum")
        layout.operator("mesh.generate_gear", icon='MODIFIER')


classes = (
    GearGeneratorProperties,
    OBJECT_OT_generate_gear,
    VIEW3D_PT_gear_generator_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gear_generator_props = bpy.props.PointerProperty(type=GearGeneratorProperties)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.gear_generator_props


if __name__ == "__main__":
    register()
