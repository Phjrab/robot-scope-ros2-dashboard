import bpy
from pathlib import Path
from mathutils import Vector
s=bpy.context.scene;c=s.camera;c.location=(4.8,1.6,2.1);c.rotation_euler=(Vector((7.8,3,.3))-c.location).to_track_quat('-Z','Y').to_euler();c.data.ortho_scale=2.4;s.render.filepath=str(Path(bpy.data.filepath).parent/'previews/parking_wall_markers.png');bpy.ops.render.render(write_still=True)
