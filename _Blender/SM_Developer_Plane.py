"""
Batch Plane Generator and FBX Exporter for Blender
--------------------------------------------------

- Generates a grid of subdivided planes for all combinations of sizes in PLANE_SIZES_CM.
- Each plane is placed in a nested collection structure: width/height (e.g., 200/200x100).
- Each collection is exported as a separate FBX file, always overwriting existing files.
- UVs are mapped using Project from View (Bounds) logic.
- Designed for Blender 4.x (tested on 4.4+).
- Formatted with Black Playground.

User Settings:
    - PLANE_SUBDIVISION_SIZE: subdivision size (meters)
    - EXPORT_BASE_DIR: where to export FBX files
    - PLANE_SIZES_CM: sizes to use (in centimeters)
    - EXPORT_TO_FBX: Set to False to skip export

Author: Jonathan Linat
Last updated: 2024-06
Tested on: Blender 4.4.3
"""

import bpy
import bmesh
import itertools
import math
import os

# === GLOBAL SETTINGS ===
PLANE_SUBDIVISION_SIZE = 0.2  # meters
EXPORT_BASE_DIR = (
    r"D:\Projects\Personal\Unreal Projects\PSXSandboxProject\_Blender\Exported"
)
PLANE_SIZES_CM = [20, 40, 60, 80, 100, 120, 140, 160, 180, 200]
EXPORT_TO_FBX = True  # Set to False to skip FBX export step
# =======================

PLANE_SIZES_M = [s / 100 for s in PLANE_SIZES_CM]
PLANE_SIZE_PAIRS = list(itertools.product(PLANE_SIZES_M, PLANE_SIZES_M))

# --- Clean up previous mesh objects and generated collections ---
remove_collections = []
for col in list(bpy.data.collections):
    if col.name.isdigit() or "x" in col.name or col.name.startswith("UCX_"):
        remove_collections.append(col)
for obj in list(bpy.data.objects):
    if obj.type == "MESH":
        bpy.data.objects.remove(obj, do_unlink=True)
for col in remove_collections:
    bpy.data.collections.remove(col)

# --- Utility: Create width and height collections, cache references ---
scene_collection = bpy.context.scene.collection
width_collections = {}
height_collections_map = {w: {} for w in PLANE_SIZES_CM}

for width_cm in PLANE_SIZES_CM:
    col_name = f"{width_cm}"
    width_collection = bpy.data.collections.get(col_name)
    if not width_collection:
        width_collection = bpy.data.collections.new(col_name)
        scene_collection.children.link(width_collection)
    width_collections[width_cm] = width_collection

    for height_cm in PLANE_SIZES_CM:
        subcol_name = f"{width_cm}x{height_cm}"
        subcollection = bpy.data.collections.get(subcol_name)
        if not subcollection:
            subcollection = bpy.data.collections.new(subcol_name)
            width_collection.children.link(subcollection)
        height_collections_map[width_cm][height_cm] = subcollection


# --- BMesh-based subdivided plane creation with Project from View (Bounds) UVs ---
def create_subdivided_plane_bmesh(width, height, name="Plane"):
    n_x = int(round(width / PLANE_SUBDIVISION_SIZE))
    n_y = int(round(height / PLANE_SUBDIVISION_SIZE))
    min_x, max_x = -width / 2, width / 2
    min_y, max_y = -height / 2, height / 2

    bm = bmesh.new()
    verts_grid = [
        [
            bm.verts.new(
                (
                    (x * PLANE_SUBDIVISION_SIZE) - width / 2,
                    (y * PLANE_SUBDIVISION_SIZE) - height / 2,
                    0,
                )
            )
            for x in range(n_x + 1)
        ]
        for y in range(n_y + 1)
    ]
    bm.verts.ensure_lookup_table()

    uv_layer = bm.loops.layers.uv.new("UVMap")

    for y in range(n_y):
        for x in range(n_x):
            v0 = verts_grid[y][x]  # bottom-left
            v1 = verts_grid[y][x + 1]  # bottom-right
            v2 = verts_grid[y + 1][x]  # top-left
            v3 = verts_grid[y + 1][x + 1]  # top-right

            # Always split from top-left to bottom-right
            tris = [(v0, v1, v2), (v1, v3, v2)]
            for tri in tris:
                try:
                    face = bm.faces.new(tri)
                except ValueError:
                    face = bm.faces.get(tri)
                for loop in face.loops:
                    vx, vy, _ = loop.vert.co
                    u = (vx - min_x) / (max_x - min_x)
                    v_uv = (vy - min_y) / (max_y - min_y)
                    loop[uv_layer].uv = (u, v_uv)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    obj.scale = (1, 1, 1)
    obj.location = (0, 0, 0)
    return obj


def create_simple_plane(width, height, name="UCX"):
    hw = width / 2
    hh = height / 2
    verts = [(-hw, -hh, 0), (hw, -hh, 0), (hw, hh, 0), (-hw, hh, 0)]
    faces = [[0, 1, 2, 3]]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.scale = (1, 1, 1)
    obj.location = (0, 0, 0)
    return obj


# --- Main creation loop ---
for width, height in PLANE_SIZE_PAIRS:
    width_cm = int(round(width * 100))
    height_cm = int(round(height * 100))
    obj_name = f"{width_cm}x{height_cm}"
    ucx_name = f"UCX_{obj_name}"
    # Create mesh objects
    obj = create_subdivided_plane_bmesh(width, height, name=obj_name)
    obj_ucx = create_simple_plane(width, height, name=ucx_name)

    # Place in the correct collection
    subcol = height_collections_map[width_cm][height_cm]
    subcol.objects.link(obj)
    subcol.objects.link(obj_ucx)

    # Unlink from scene root collection if present
    for o in (obj, obj_ucx):
        try:
            bpy.context.scene.collection.objects.unlink(o)
        except Exception:
            pass


# --- Sorting: width collections, height collections, objects (all alphanum) ---
def alnum_key(s):
    return [int(part) if part.isdigit() else part for part in s.split("x")]


width_coll_names = sorted(
    [col.name for col in scene_collection.children if col.name.isdigit()],
    key=lambda n: int(n),
)
for col in list(scene_collection.children):
    if col.name in width_coll_names:
        scene_collection.children.unlink(col)
for col_name in width_coll_names:
    scene_collection.children.link(bpy.data.collections[col_name])
    width_col = bpy.data.collections[col_name]
    height_coll_names = sorted(
        [subcol.name for subcol in width_col.children], key=alnum_key
    )
    for subcol in list(width_col.children):
        width_col.children.unlink(subcol)
    for subcol_name in height_coll_names:
        width_col.children.link(bpy.data.collections[subcol_name])
        subcol = bpy.data.collections[subcol_name]
        objs_sorted = sorted(subcol.objects, key=lambda o: o.name)
        for obj in list(subcol.objects):
            subcol.objects.unlink(obj)
        for obj in objs_sorted:
            subcol.objects.link(obj)

print("Plane generation and organization complete!")


def find_layer_collection(layer_coll, coll):
    if layer_coll.collection == coll:
        return layer_coll
    for child in layer_coll.children:
        res = find_layer_collection(child, coll)
        if res:
            return res
    return None


# --- Batch Export ---
if EXPORT_TO_FBX:
    print("Now exporting FBX files...")

    width_collections = [col for col in scene_collection.children if col.name.isdigit()]
    width_collections = sorted(width_collections, key=lambda c: int(c.name))

    for width_col in width_collections:
        width_cm = width_col.name
        for subcol in sorted(width_col.children, key=lambda c: alnum_key(c.name)):
            if "x" not in subcol.name:
                continue
            height_cm = subcol.name.split("x")[1]
            objects_to_export = [obj for obj in subcol.objects if obj.type == "MESH"]
            if not objects_to_export:
                continue

            # Find and set subcol as active collection (robustly)
            target_layer_collection = find_layer_collection(
                bpy.context.view_layer.layer_collection, subcol
            )
            if not target_layer_collection:
                print(f"LayerCollection for {subcol.name} not found, skipping.")
                continue
            bpy.context.view_layer.active_layer_collection = target_layer_collection

            # Create export path
            export_dir = os.path.join(EXPORT_BASE_DIR, width_cm, height_cm)
            os.makedirs(export_dir, exist_ok=True)
            fbx_filename = f"SM_Developer_Plane_{subcol.name}.fbx"
            export_path = os.path.join(export_dir, fbx_filename)

            # --- Cleanup logic: always overwrite ---
            if os.path.isfile(export_path):
                try:
                    os.remove(export_path)
                    print(f"Removed old file: {export_path}")
                except Exception as e:
                    print(f"Could not remove old file {export_path}: {e}")

            # Set the main plane as active, if possible
            main_plane_name = subcol.name  # e.g. "200x100"
            main_plane = next(
                (obj for obj in objects_to_export if obj.name == main_plane_name), None
            )
            if main_plane:
                bpy.context.view_layer.objects.active = main_plane
            else:
                bpy.context.view_layer.objects.active = objects_to_export[0]

            bpy.ops.export_scene.fbx(
                filepath=export_path,
                use_active_collection=True,
                object_types={"MESH"},
                mesh_smooth_type="FACE",
            )

            print(f"Exported {export_path}")

    print("Batch FBX export complete.")
else:
    print("EXPORT_TO_FBX is set to False. Skipping FBX export step.")
