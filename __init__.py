#  ***** GPL LICENSE BLOCK *****
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#  All rights reserved.
#  ***** GPL LICENSE BLOCK *****

bl_info = {
    "name": "Scalable Vector Graphics (SVG) 1.1 Format Exporter",
    "author": "Mikalai Abramau",
    "blender": (2, 6, 3),
    "location": "File > Export > Scalable Vector Graphics (.svg) Exporter",
    "description": "Export selected objects as SVG. Supports meshes and curves.",
    "warning": "Under construction",
    "version": (0, 0, 1),
    "category": "Import-Export"}

import bpy
import math
import mathutils
import copy

from copy import deepcopy
from mathutils import Matrix, Vector
from math import tan, atan

#   
#   calculates typical perspective projection matrix
#   based on camera field of view, aspect ratio and
#   near and far clipping planes
#
def make_projection_matrix(fovx, aspect, znear, zfar):
    e = 1.0 / tan(fovx / 2.0)
    fovy = 2.0 * atan(aspect / e)
    xScale = 1.0 / tan(0.5 * fovy)
    yScale = xScale * aspect
    
    m = Matrix()
    
    m[0][0] = xScale
    m[0][1] = 0.0
    m[0][2] = 0.0
    m[0][3] = 0.0
    
    m[1][0] = 0.0;
    m[1][1] = yScale
    m[1][2] = 0.0
    m[1][3] = 0.0
    
    m[2][0] = 0.0
    m[2][1] = 0.0
    m[2][2] = (zfar + znear) / (znear - zfar)
    m[2][3] = -1.0
    
    m[3][0] = 0.0
    m[3][1] = 0.0
    m[3][2] = (2.0 * zfar * znear) / (znear - zfar)
    m[3][3] = 0.0
    
    return m

class SVGVertex: 
    def __init__(self):
        self.position = Vector()
        return
 
class SVGFace:
    def __init__(self, polygon):
        self.vertices = polygon.vertices   
        self.normal = polygon.normal
        return

class SVGEdge:
    def __init__(self):
        self.vertex = []
        return
                   
#
#   
#
class SVGMesh:
    def __init__(self, mesh):
        self.projected_vertices = []
        self.vertices = []
        self.edges = set()
        self.faces = []       
        self.proj = Matrix()
        self.view = Matrix()
        self.world = Matrix()
        
        for v in mesh.vertices:
            vertex = SVGVertex()
            vertex.position = v.co
            self.vertices.append(vertex)
            
        for f in mesh.polygons:
            face = SVGFace(f)
            self.faces.append(face)

        return
    
    def project_vertices(self, proj, view, world):
        self.proj = proj
        self.view = view
        self.world = world
        for v in self.vertices:
            p =  proj * view * world * v.position
            p /= p[2]
    
            #   scale and centralise
            screen_width = bpy.context.scene.render.resolution_x
            screen_height = bpy.context.scene.render.resolution_y
            
            p[0] = screen_width / 2 + p[0] / 2 * screen_width
            p[1] = screen_height / 2 + -p[1] / 2 * screen_height
            
            #   debug output            
            proj_v = SVGVertex();
            proj_v.position = p                    
            self.projected_vertices.append(proj_v)
            
        return
        
    def sort_faces(self):        
        self.faces = sorted(self.faces, key = self.cmp, reverse = True)
        return
    
    def cmp(self, face):
        c = Vector()
        for v in face.vertices:
            c = c + self.view * self.world * self.vertices[v].position
        c /= len(face.vertices)
        print(c.length)
        return c.length
    
    def front_faces(self):        
        #   get normal transform matrix
        normal_matrix = (self.view * self.world).to_3x3().inverted().transposed()
    
        result = []    
        for face in self.faces:
            normal = normal_matrix * face.normal
            #   calculate dot product
            cos_angle = normal * Vector((0,0,1))
    
            #   skip this polygon
            if (cos_angle <= 0):
                continue
                           
            v = []
            for vert_index in face.vertices:                
                v.append(self.projected_vertices[vert_index])
            result.append(v)
            
        return result    
    
    def all_faces(self):
        result = []    
        for face in self.faces:                      
            v = []
            for vert_index in face.vertices:                
                v.append(self.projected_vertices[vert_index])
            result.append(v)            
        return result   
    
    def calculate_edges(self):
        return 
    
#
#   contains view and projection matrices
#   ortho projection is not supported yet
class SVGCamera:
       
    def __init__(self):
        self.view_matrix = Matrix()
        self.proj_matrix = Matrix()      
    
    def make_camera(self, blender_camera):
        self.view_matrix = blender_camera.matrix_world.inverted()
        self.proj_matrix = Matrix()
                
        if blender_camera.data.type == 'PERSP':
            #   build perspective projection
            screen_width = bpy.context.scene.render.resolution_x
            screen_height = bpy.context.scene.render.resolution_y
            aspect = screen_width / screen_height
            fovx = blender_camera.data.angle_x
            near = blender_camera.data.clip_start
            far = blender_camera.data.clip_end
            self.proj_matrix = make_projection_matrix(fovx, aspect, near, far)
        elif blender_camera.data.type == 'ORTHO':
            print("WARNING: Orthoprojection is not supported yet")
            pass
        else:
            print("Unsupported camera type")  
        
        print("Camera made")
        print("View matrix:\n", self.view_matrix)
        print("Projection matrix:\n", self.proj_matrix)

        
class SVGWriter:
    def __init__(self, policy):
        self.policy = policy
        
    #
    #   opens file and call export functions
    #
    def run(self):
        if not self.check_data():
            print("Can't export scene")
            return {'FINISHED'}
        
        print("Export scene to SVG")
             
        self.file = open(self.policy.file_path, 'w', encoding='utf-8')
        self.export_scene()    
        self.file.close()
    
        return {'FINISHED'}
    
    #
    #   performs scene check for ability to be exported
    #
    def check_data(self):
        print("Check scene")
        if bpy.context.scene.camera == None:
            print("Can't export without scene camera set")
            return False
        
        if len(bpy.context.selected_objects) == 0:
            print("Nothing selected to export")
            return False
        
        return True
    
    #
    #   data exporting goes here
    #
    def export_scene(self):
        self.begin()
        
        #   retrieve camera
        self.camera = SVGCamera()
        self.camera.make_camera(bpy.context.scene.camera)
        
        #   export every object 
        for object in bpy.context.selected_objects:
            self.export_object(object)
            
        self.end()
        return {'FINISHED'}
        
        #
    #   creates xml header, and starts svg tag
    #    
    def begin(self):
        self.file.write('<?xml version="1.0" standalone="no"?>\n\
    <!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n')
    
        self.file.write('<svg xmlns="http://www.w3.org/2000/svg" version="1.1"')
        self.file.write(' width="%f"' % (bpy.context.scene.render.resolution_x))
        self.file.write(' height="%f"' % (bpy.context.scene.render.resolution_y)) 
        self.file.write('>\n')
        
        return {'FINISHED'}
    
    #
    #   close svg tag
    #
    def end(self):
        self.file.write('</svg>')
        return
    
    #
    #   ployline
    #
    def polyline(self, points):
        self.file.write('<polyline points="')
        for p in points:
            self.file.write("%f,%f " % (p[0], p[1]))
        self.file.write('"\n')
        self.file.write('style="fill:none;stroke:black;stroke-width:3" />\n')
        return 
    
    #
    #   ployline
    #
    def polygon(self, points):
        self.file.write('<polygon points="')
        for p in points:
           # print("Write: ", p.position[0])
            self.file.write("%f,%f " % (p.position[0], p.position[1]))
        self.file.write('"\n')           
        if self.policy.wireframe:
            self.file.write('style="fill:none;stroke:black;stroke-width:%f" />\n' % (self.policy.line_width))
        else:
          self.file.write('style="fill:rgb(255,255,255); stroke:black;stroke-width:%f" />\n' % (self.policy.line_width))
        return 
    
    #
    #   exports mesh to svg
    #
    def export_mesh(self, world_matrix, mesh):
        svg_mesh = SVGMesh(mesh)
        
        svg_mesh.project_vertices(self.camera.proj_matrix, self.camera.view_matrix, world_matrix)   
        print("PROJECTED 2 : ", svg_mesh.projected_vertices[0].position)
        
        if self.policy.sort_zview:
            svg_mesh.sort_faces()
                        
        if self.policy.edge_detection == 'OPT_A':
            if self.policy.back_culling:
                f = svg_mesh.front_faces()
                print("Front faces count: ", len(f))
                for v in f:
                    self.polygon(v)
            else:
                f = svg_mesh.all_faces()
                print("Front faces count: ", len(f))
                for v in f:
                    self.polygon(v)
        elif self.policy.edge_detection == 'OPT_B':
            print("Warning: edge detection algorithm is not supported")
        else:
            print("Edge detection algorithm is not supported")
                       
        return
       
    #
    #   exports object
    #    
    def export_object(self, object):
        if object.data == None:
            print("Can't export object with empty data")
            return
        
        if type(object.data) == bpy.types.Mesh:
            self.export_mesh(object.matrix_world, object.data)
        else:
            print("Can't export data of specified type")
                    
        return
    
    

# ExportHelper is a helper class, defines filename and
# invoke() function which calls the file selector.
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty, FloatProperty
from bpy.types import Operator

#
#   class contains different option of exporting data
#
class SVGExportPolicy:    
    def __init__(self):
        #   filepath to export data 
        self.file_path = ""         
        #   back culling flag
        self.back_culling = False
        #   direction of the camera
        self.camera_dir = Vector((0,0,1))
        #   sorting of faces by z depth value
        self.sort_zview = True
        #   wirefrime mode
        self.wireframe = False
        #   line width
        self.line_width = 1
        #   edge detection algorithm
        self.edge_detection = 'OPT_B'

#
#   Exporter implementation
#
class SVGExporter(Operator, ExportHelper):
    """Export selected objects as projections in vector form to SVG format"""
    bl_idname = "export_svg.svg"  
    bl_label = "Export in SVG"

    # ExportHelper mixin class uses this
    filename_ext = ".svg"

    filter_glob = StringProperty(
            default="*.svg",
            options={'HIDDEN'},
            )

    #   properties goes here
    cull_back = BoolProperty(
            name="Enable back culling",
            description="Faces that are oriented backward the camera will be culled",
            default=True,
            )

    #   wire frame
    wireframe = BoolProperty(
            name = "Enable wireframe mode",
            description = "Each polygon is exported in as a polyline",
            default = False,
            )
          
    #   enable auto z sort
    zsort = BoolProperty(
            name = "Enable z-sort",
            description = "Enable ",
            default = True,
            )  
            
    #   set up width of lines
    line_width = FloatProperty( 
            name = "Line width",
            description = "Set up edges width",
            options = {'ANIMATABLE'},
            subtype = 'NONE',
            unit = 'LENGTH',
            min = 0.001,
            max = 10.0,
            default = 1)
            
    edge_detection = EnumProperty(
        name="Edge detection",
        description="Select edge detection algorithm",
        items=(('OPT_A', "Algorithm 1", "No edge detection"),
               ('OPT_B', "Algorithm 2", "Simple edge detection")),
        default='OPT_A',
        )
                            

    def execute(self, context):
        options = SVGExportPolicy()
        options.file_path = self.filepath
        options.back_culling = self.cull_back
        options.sort_zview = self.zsort
        options.wireframe = self.wireframe
        options.line_width = self.line_width
        options.edge_detection = self.edge_detection
        
        writer = SVGWriter(options)
        return writer.run()


# Only needed if you want to add into a dynamic menu
def menu_func_export(self, context):
    self.layout.operator(SVGExporter.bl_idname, text="Text Export Operator")


def register():
    bpy.utils.register_class(SVGExporter)
    bpy.types.INFO_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_class(SVGExporter)
    bpy.types.INFO_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
    register()

# test call
bpy.ops.export_svg.svg('INVOKE_DEFAULT')
