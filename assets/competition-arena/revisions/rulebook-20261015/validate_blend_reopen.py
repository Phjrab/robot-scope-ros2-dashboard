import bpy,json,math
from pathlib import Path
p=Path(bpy.data.filepath).parent
objects=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert objects
for o in objects:
 assert o.data.vertices and o.data.polygons,o.name
 assert all(math.isfinite(a)for v in o.data.vertices for a in v.co),o.name
result=dict(status='PASS',validation_type='BLENDER_REOPEN',version=bpy.app.version_string,mesh_count=len(objects),nonfinite_or_empty_meshes=0)
(p/'blend_reopen_validation.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
