bl_info = {
    "name": "Auto Blink ShapKey",
    "author": "Sergio ReOli",
    "version": (1, 2, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > Auto Blink Shapekey",
    "description": "Generates randomized blink keyframes on a shape key, adapting timing to the scene FPS",
    "category": "Animation",
}

import json
import random

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup

# ---------------------------------------------------------------------------
# Blink presets
# All times are in SECONDS, so they stay correct at any scene FPS.
# "interval" is measured from the start of one blink to the start of the next.
# ---------------------------------------------------------------------------
BLINK_PRESETS = {
    "NATURAL": {
        "interval_min": 3.0, "interval_max": 5.0,
        "close_time": 0.06, "hold_time": 0.04, "open_time": 0.12,
        "double_chance": 0.10,
    },
    "LIVELY": {
        "interval_min": 2.0, "interval_max": 3.0,
        "close_time": 0.04, "hold_time": 0.04, "open_time": 0.08,
        "double_chance": 0.25,
    },
    "CALM": {
        "interval_min": 5.0, "interval_max": 8.0,
        "close_time": 0.08, "hold_time": 0.04, "open_time": 0.14,
        "double_chance": 0.05,
    },
    "SLEEPY": {
        "interval_min": 4.0, "interval_max": 7.0,
        "close_time": 0.15, "hold_time": 0.08, "open_time": 0.25,
        "double_chance": 0.0,
    },
}

BLINK_PRESET_ITEMS = [
    ("NATURAL", "Natural", "Blink every 3-5 seconds"),
    ("LIVELY", "Lively / Nervous", "Fast blinks every 2-3 seconds, frequent double blinks"),
    ("CALM", "Calm", "Slow, relaxed blinks every 5-8 seconds"),
    ("SLEEPY", "Sleepy", "Slow, heavy blinks every 4-7 seconds"),
    ("CUSTOM", "Custom", "Your own settings"),
]

# ---------------------------------------------------------------------------
# Eye look presets (resting shape key value = how open the eyes are most of the time)
# The shape key closes the eye, so: 0.0 = base shape, 1.0 = fully closed.
# ---------------------------------------------------------------------------
EYE_LOOKS = {
    "WIDE": 0.0,
    "OPEN": 0.2,
    "HALF": 0.4,
    "DROOPY": 0.8,
}

EYE_LOOK_ITEMS = [
    ("WIDE", "Wide-eyed (0.0)", "Eyes wide open: alert, surprised, intense"),
    ("OPEN", "Open (0.2)", "Normal, fully open eyes"),
    ("HALF", "Slightly Closed (0.4)", "Relaxed, calm or smug look"),
    ("DROOPY", "Almost Closed (0.8)", "Heavy eyelids: sleepy, bored, tired"),
    ("CUSTOM", "Custom", "Pick your own resting value"),
]

_applying_preset = False


def _apply_blink_preset(self, context):
    global _applying_preset
    data = BLINK_PRESETS.get(self.preset)
    if data is None:
        return
    _applying_preset = True
    try:
        for name, value in data.items():
            setattr(self, name, value)
    finally:
        _applying_preset = False


def _mark_blink_custom(self, context):
    if not _applying_preset and self.preset != "CUSTOM":
        self.preset = "CUSTOM"


def _apply_eye_look(self, context):
    global _applying_preset
    value = EYE_LOOKS.get(self.eye_look)
    if value is None:
        return
    _applying_preset = True
    try:
        self.rest_value = value
    finally:
        _applying_preset = False


def _mark_eye_custom(self, context):
    if not _applying_preset and self.eye_look != "CUSTOM":
        self.eye_look = "CUSTOM"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
class AutoBlinkSettings(PropertyGroup):
    preset: EnumProperty(
        name="Blink Style", items=BLINK_PRESET_ITEMS, default="NATURAL",
        update=_apply_blink_preset,
    )
    eye_look: EnumProperty(
        name="Eye Look", items=EYE_LOOK_ITEMS, default="OPEN",
        update=_apply_eye_look,
    )
    rest_value: FloatProperty(
        name="Rest Value",
        description="Shape key value while the eyes are not blinking "
                    "(0 = wide-eyed, 1 = fully closed). Defines the character's default look",
        default=0.2, min=0.0, max=1.0, subtype='FACTOR', update=_mark_eye_custom,
    )
    closed_value: FloatProperty(
        name="Closed Value",
        description="Shape key value at the peak of a blink",
        default=1.0, min=0.0, max=1.0, subtype='FACTOR',
    )
    shape_key: StringProperty(
        name="Shape Key", description="Shape key that closes the eye", default="Blink"
    )

    frame_start: IntProperty(name="Start", description="First frame of the blink range", default=0, min=0)
    frame_end: IntProperty(name="End", description="Last frame of the blink range", default=100, min=1)

    interval_min: FloatProperty(
        name="Min Interval", description="Minimum time between blink starts (seconds)",
        default=3.0, min=0.2, soft_max=15.0, unit='TIME_ABSOLUTE', update=_mark_blink_custom,
    )
    interval_max: FloatProperty(
        name="Max Interval", description="Maximum time between blink starts (seconds)",
        default=5.0, min=0.2, soft_max=15.0, unit='TIME_ABSOLUTE', update=_mark_blink_custom,
    )
    close_time: FloatProperty(
        name="Close", description="Time to close the eye (seconds)",
        default=0.06, min=0.0, soft_max=0.5, precision=3, unit='TIME_ABSOLUTE',
        update=_mark_blink_custom,
    )
    hold_time: FloatProperty(
        name="Hold", description="Time the eye stays closed (seconds)",
        default=0.04, min=0.0, soft_max=0.5, precision=3, unit='TIME_ABSOLUTE',
        update=_mark_blink_custom,
    )
    open_time: FloatProperty(
        name="Open", description="Time to reopen the eye (seconds)",
        default=0.12, min=0.0, soft_max=0.8, precision=3, unit='TIME_ABSOLUTE',
        update=_mark_blink_custom,
    )
    double_chance: FloatProperty(
        name="Double Blink Chance", description="Probability of a quick second blink",
        default=0.10, min=0.0, max=1.0, subtype='FACTOR', update=_mark_blink_custom,
    )
    seed: IntProperty(
        name="Seed", description="Random seed (0 = different result every time)",
        default=0, min=0,
    )
    overwrite_other: BoolProperty(
        name="Overwrite Other Keys",
        description="Also delete keyframes inside the frame range that were NOT created by "
                    "Auto Blink. When off, generation is cancelled if such keyframes exist",
        default=False,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def scene_fps(scene):
    return scene.render.fps / scene.render.fps_base


def to_frames(seconds, fps, minimum=0):
    return max(minimum, int(round(seconds * fps)))


def blink_durations(s, fps):
    close_f = to_frames(s.close_time, fps, 1)
    hold_f = to_frames(s.hold_time, fps, 0)
    open_f = to_frames(s.open_time, fps, 1)
    return close_f, hold_f, open_f


# Properties restored to their initial values by "Clear Blink Keys".
# The shape key selection is kept, since it is the target and not a setting.
RESET_PROPS = (
    "preset", "eye_look", "rest_value", "closed_value",
    "frame_start", "frame_end",
    "interval_min", "interval_max", "close_time", "hold_time", "open_time",
    "double_chance", "seed", "overwrite_other",
)


def reset_settings(s):
    global _applying_preset
    _applying_preset = True  # avoid switching presets to "Custom" while resetting
    try:
        for name in RESET_PROPS:
            s.property_unset(name)
    finally:
        _applying_preset = False


def get_target(context, s):
    """Returns (shape_keys_datablock, key_block, error_message)."""
    obj = context.active_object
    if obj is None or obj.type != 'MESH' or obj.data.shape_keys is None:
        return None, None, "Select a mesh object that has shape keys."
    keys = obj.data.shape_keys
    block = keys.key_blocks.get(s.shape_key)
    if block is None:
        return None, None, f'Shape key "{s.shape_key}" not found.'
    return keys, block, None


def find_fcurve(keys, data_path):
    ad = keys.animation_data
    if ad is None or ad.action is None:
        return None
    return ad.action.fcurves.find(data_path)


def ensure_fcurve(keys, data_path):
    ad = keys.animation_data or keys.animation_data_create()
    if ad.action is None:
        ad.action = bpy.data.actions.new(name=f"{keys.name}Action")
    fcurve = ad.action.fcurves.find(data_path)
    if fcurve is None:
        fcurve = ad.action.fcurves.new(data_path)
    return fcurve


# --- Record of the keyframes created by this addon -------------------------
# Stored on the shape keys datablock as JSON, so it is saved with the .blend:
#   {"<shape key name>": [[frame, value], ...]}
RECORD_PROP = "auto_blink_keys"


def load_record(keys, name):
    raw = keys.get(RECORD_PROP)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return {int(f): float(v) for f, v in data.get(name, [])}


def save_record(keys, name, table):
    try:
        data = json.loads(keys.get(RECORD_PROP) or "{}")
    except ValueError:
        data = {}
    if table:
        data[name] = [[f, v] for f, v in sorted(table.items())]
    else:
        data.pop(name, None)
    if data:
        keys[RECORD_PROP] = json.dumps(data)
    elif RECORD_PROP in keys:
        del keys[RECORD_PROP]


def is_mine(keyframe, record):
    """True only if the keyframe is at a recorded frame AND still has the recorded value."""
    f = int(round(keyframe.co.x))
    return (
        f in record
        and abs(keyframe.co.x - f) < 1e-3
        and abs(keyframe.co.y - record[f]) < 1e-3
    )


def remove_keyframes(fcurve, predicate):
    pts = fcurve.keyframe_points
    removed = 0
    for i in reversed(range(len(pts))):
        if predicate(pts[i]):
            pts.remove(pts[i])
            removed += 1
    return removed


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------
class AUTOBLINK_OT_generate(Operator):
    bl_idname = "autoblink.generate"
    bl_label = "Generate Blinks"
    bl_description = ("Insert randomized blink keyframes on the chosen shape key. "
                      "Previous Auto Blink keyframes are replaced")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        s = scene.auto_blink

        keys, block, error = get_target(context, s)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        f_start, f_end = s.frame_start, s.frame_end
        if f_end <= f_start:
            self.report({'ERROR'}, "End frame must be greater than start frame.")
            return {'CANCELLED'}

        rest = s.rest_value
        closed = s.closed_value
        if closed - rest < 0.05:
            self.report(
                {'ERROR'},
                "Closed Value must be at least 0.05 higher than Rest Value, "
                "otherwise the blink would not be visible.",
            )
            return {'CANCELLED'}

        data_path = block.path_from_id("value")
        fcurve = find_fcurve(keys, data_path)
        record = load_record(keys, block.name)

        # Safety check: keyframes in range that were not created by this addon
        if fcurve is not None:
            foreign = [
                kp for kp in fcurve.keyframe_points
                if f_start <= kp.co.x <= f_end and not is_mine(kp, record)
            ]
            if foreign and not s.overwrite_other:
                self.report(
                    {'ERROR'},
                    f"{len(foreign)} keyframe(s) in the range were not created by Auto Blink. "
                    "Change the range or enable 'Overwrite Other Keys' (Advanced).",
                )
                return {'CANCELLED'}

        fps = scene_fps(scene)
        rng = random.Random(s.seed if s.seed else None)

        close_f, hold_f, open_f = blink_durations(s, fps)
        dur = close_f + hold_f + open_f
        lo, hi = sorted((s.interval_min, s.interval_max))
        imin = to_frames(lo, fps, dur + 1)
        imax = max(imin, to_frames(hi, fps, dur + 1))

        # Build the keyframe table {frame: value}
        table = {}
        blink_count = 0

        def add_blink(start):
            table[start] = rest
            table[start + close_f] = closed
            if hold_f > 0:
                table[start + close_f + hold_f] = closed
            table[start + dur] = rest

        first_lo = to_frames(0.2, fps, 1)
        first_hi = max(first_lo, int(imin * 0.5))
        group_start = f_start + rng.randint(first_lo, first_hi)

        while group_start + dur <= f_end:
            add_blink(group_start)
            blink_count += 1
            group_end = group_start + dur

            if rng.random() < s.double_chance:
                gap = rng.randint(max(2, to_frames(0.08, fps)), max(3, to_frames(0.2, fps)))
                second = group_end + gap
                if second + dur <= f_end:
                    add_blink(second)
                    blink_count += 1
                    group_end = second + dur

            group_start = max(group_start + rng.randint(imin, imax), group_end + 2)

        # Rest value at the very beginning and end: the character keeps its default look
        table.setdefault(f_start, rest)
        table.setdefault(f_end, rest)

        # Write to the F-Curve
        if fcurve is None:
            fcurve = ensure_fcurve(keys, data_path)
        else:
            # Remove previous Auto Blink keys (anywhere) and, optionally, other keys in range
            remove_keyframes(
                fcurve,
                lambda kp: is_mine(kp, record)
                or (s.overwrite_other and f_start <= kp.co.x <= f_end),
            )

        for frame, value in sorted(table.items()):
            fcurve.keyframe_points.insert(frame, value, options={'REPLACE'})

        # Fast close (ease out), softer open (ease in) - only on keys we created
        pts = fcurve.keyframe_points
        for i in range(len(pts) - 1):
            cur, nxt = pts[i], pts[i + 1]
            if int(round(cur.co.x)) not in table:
                continue
            if cur.co.y < nxt.co.y:
                cur.interpolation = 'SINE'
                cur.easing = 'EASE_OUT'
            elif cur.co.y > nxt.co.y:
                cur.interpolation = 'SINE'
                cur.easing = 'EASE_IN'
            else:
                cur.interpolation = 'LINEAR'
        fcurve.update()

        save_record(keys, block.name, table)

        self.report(
            {'INFO'},
            f"{blink_count} blink(s) added between frames {f_start}-{f_end} "
            f"({fps:.3g} FPS, rest value {rest:.2f})",
        )
        return {'FINISHED'}


class AUTOBLINK_OT_clear(Operator):
    bl_idname = "autoblink.clear"
    bl_label = "Clear Blink Keys"
    bl_description = ("Remove ONLY the keyframes created by Auto Blink on this shape key "
                      "(keyframes you added or edited yourself are kept) "
                      "and reset the addon settings to their initial values")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.auto_blink

        keys, block, error = get_target(context, s)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        record = load_record(keys, block.name)
        if not record:
            reset_settings(s)
            self.report({'INFO'}, "No Auto Blink keyframes to remove. Settings were reset.")
            return {'FINISHED'}

        fcurve = find_fcurve(keys, block.path_from_id("value"))
        removed = 0
        if fcurve is not None:
            removed = remove_keyframes(fcurve, lambda kp: is_mine(kp, record))
            if len(fcurve.keyframe_points) == 0:
                keys.animation_data.action.fcurves.remove(fcurve)
            else:
                fcurve.update()

        save_record(keys, block.name, {})
        reset_settings(s)
        self.report({'INFO'}, f"Removed {removed} Auto Blink keyframe(s). Settings were reset.")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
class AUTOBLINK_PT_main(Panel):
    bl_label = "Auto Blink"
    bl_idname = "AUTOBLINK_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Auto Blink"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        s = scene.auto_blink
        obj = context.active_object

        fps = scene_fps(scene)
        fps_text = f"{fps:.3f}".rstrip("0").rstrip(".")
        layout.label(text=f"Scene FPS: {fps_text}", icon='TIME')

        # Target
        keys = None
        if obj and obj.type == 'MESH' and obj.data.shape_keys:
            keys = obj.data.shape_keys
            layout.prop_search(s, "shape_key", keys, "key_blocks", text="Shape Key")
        else:
            layout.label(text="Select a mesh with shape keys", icon='ERROR')

        # Eye look (character personality)
        box = layout.box()
        box.label(text="Default Eye Look", icon='HIDE_OFF')
        box.prop(s, "eye_look", text="")
        box.prop(s, "rest_value", text="Rest Value", slider=True)
        if s.closed_value - s.rest_value < 0.05:
            box.label(text="Rest Value is too close to Closed Value", icon='ERROR')

        # Blink style
        layout.prop(s, "preset")

        # Range
        row = layout.row(align=True)
        row.prop(s, "frame_start")
        row.prop(s, "frame_end")

        # Summary in frames at the current FPS
        close_f, hold_f, open_f = blink_durations(s, fps)
        dur = close_f + hold_f + open_f
        lo, hi = sorted((s.interval_min, s.interval_max))
        box = layout.box()
        box.label(text=f"Blink length: {dur} frames")
        box.label(text=f"Every {to_frames(lo, fps, dur + 1)}-{to_frames(hi, fps, dur + 1)} frames")
        if keys is not None and s.shape_key in keys.key_blocks:
            count = len(load_record(keys, s.shape_key))
            box.label(text=f"Auto Blink keyframes: {count}")

        layout.prop(s, "seed")

        col = layout.column(align=True)
        col.scale_y = 1.4
        col.operator("autoblink.generate", icon='HIDE_OFF')
        layout.operator("autoblink.clear", icon='X')


class AUTOBLINK_PT_advanced(Panel):
    bl_label = "Advanced"
    bl_idname = "AUTOBLINK_PT_advanced"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Auto Blink"
    bl_parent_id = "AUTOBLINK_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        s = context.scene.auto_blink

        col = layout.column(align=True)
        col.prop(s, "interval_min")
        col.prop(s, "interval_max")

        col = layout.column(align=True)
        col.prop(s, "close_time")
        col.prop(s, "hold_time")
        col.prop(s, "open_time")

        layout.prop(s, "double_chance")
        layout.prop(s, "closed_value", slider=True)
        layout.prop(s, "overwrite_other")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
classes = (
    AutoBlinkSettings,
    AUTOBLINK_OT_generate,
    AUTOBLINK_OT_clear,
    AUTOBLINK_PT_main,
    AUTOBLINK_PT_advanced,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.auto_blink = PointerProperty(type=AutoBlinkSettings)


def unregister():
    del bpy.types.Scene.auto_blink
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
