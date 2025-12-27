PARAMS = {{ PARAMS_JSON }}

import os
import traceback

import FreeCAD as App
import Part

try:
    import FreeCADGui as Gui
except ImportError:  # pragma: no cover - headless render may skip GUI
    Gui = None


def ensure_output_dir() -> str:
    output_dir = os.environ.get("FREECAD_OUTPUT_DIR", "/workspace/outputs")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def build_seal_shape(params: dict):
    outer_dia = float(params.get("outer_dia", 52.0))
    inner_dia = float(params.get("inner_dia", 30.0))
    lip_height = float(params.get("lip_height", 6.0))
    lip_thickness = float(params.get("lip_thickness", 2.5))
    body_width = float(params.get("body_width", 8.0))

    outer_radius = outer_dia / 2.0 / 10.0  # convert mm to cm to keep FreeCAD numerically stable
    inner_radius = inner_dia / 2.0 / 10.0

    doc = App.ActiveDocument or App.newDocument("SealRender")

    profile_points = [
        App.Vector(inner_radius, 0, 0),
        App.Vector(inner_radius, body_width / 10.0, 0),
        App.Vector(outer_radius - lip_thickness / 10.0, body_width / 10.0, 0),
        App.Vector(outer_radius, lip_height / 10.0, 0),
        App.Vector(outer_radius, 0, 0),
        App.Vector(inner_radius, 0, 0),
    ]

    wire = Part.makePolygon(profile_points)
    face = Part.Face(wire)
    axis = App.Vector(0, 1, 0)
    center = App.Vector(0, 0, 0)
    solid = face.revolve(center, axis, 360)

    part_obj = doc.addObject("Part::Feature", "RadialSeal")
    part_obj.Shape = solid
    doc.recompute()
    return part_obj


def export_step(part_obj, output_dir: str) -> str:
    step_path = os.path.join(output_dir, "seal.step")
    Part.export([part_obj], step_path)
    return step_path


def export_png(output_dir: str) -> str | None:
    if Gui is None:
        return None
    Gui.showMainWindow()
    view = Gui.activeDocument().activeView()
    view.fitAll()
    png_path = os.path.join(output_dir, "seal.png")
    view.saveImage(png_path, 1920, 1080, "Transparent")
    return png_path


def main() -> None:
    params = PARAMS or {}
    output_dir = ensure_output_dir()
    doc = App.newDocument("SealRenderJob")
    try:
        part_obj = build_seal_shape(params)
        step_path = export_step(part_obj, output_dir)
        png_path = export_png(output_dir)
        print(f"STEP file written to {step_path}")
        if png_path:
            print(f"PNG render written to {png_path}")
        else:
            print("PNG render skipped (FreeCADGui unavailable).")
    except Exception as exc:  # pragma: no cover - diagnostic fallback
        traceback.print_exc()
        raise
    finally:
        App.closeDocument(doc.Name)


if __name__ == "__main__":
    main()
