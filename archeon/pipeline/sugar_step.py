"""Runs one SuGaR sub-stage in its own process (so GPU memory is released between sub-stages).

Invoked by `archeon.pipeline.sugar` as `python -m archeon.pipeline.sugar_step <step> ...` with the scene's
work directory as cwd (SuGaR writes to ./output/...) and the SuGaR checkout on PYTHONPATH. The arguments
mirror what SuGaR's own train.py passes to each function. Completed sub-stage output paths are recorded
in a JSON state file so the next sub-stage (and retries) can pick them up.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["coarse", "mesh", "refine", "texture"])
    parser.add_argument("--scene", required=True, help="COLMAP dataset dir (images/ + sparse/0)")
    parser.add_argument("--checkpoint", required=True, help="vanilla 3DGS model dir")
    parser.add_argument("--iteration", type=int, required=True, help="3DGS iteration to load")
    parser.add_argument("--state", required=True)
    parser.add_argument("--n-vertices", type=int, required=True)
    parser.add_argument("--gaussians-per-triangle", type=int, required=True)
    parser.add_argument("--refinement-iterations", type=int, required=True)
    args = parser.parse_args()

    state_path = Path(args.state)
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    # SuGaR derives output names from the last path component and wants a trailing separator on checkpoints.
    scene = str(Path(args.scene).resolve())
    checkpoint = str(Path(args.checkpoint).resolve()) + os.sep
    common = {"scene_path": scene, "checkpoint_path": checkpoint, "iteration_to_load": args.iteration,
              "eval": False, "gpu": 0}

    if args.step == "coarse":
        from sugar_trainers.coarse_density_and_dn_consistency import (
            coarse_training_with_density_regularization_and_dn_consistency,
        )
        state["coarse"] = coarse_training_with_density_regularization_and_dn_consistency(AttrDict({
            **common, "output_dir": None, "estimation_factor": 0.2, "normal_factor": 0.2,
            "white_background": False,
        }))
    elif args.step == "mesh":
        from sugar_extractors.coarse_mesh import extract_mesh_from_coarse_sugar
        state["coarse_mesh"] = extract_mesh_from_coarse_sugar(AttrDict({
            **common, "coarse_model_path": state["coarse"], "surface_level": 0.3,
            "decimation_target": args.n_vertices, "project_mesh_on_surface_points": True,
            "mesh_output_dir": None, "bboxmin": None, "bboxmax": None, "center_bbox": True,
            "use_centers_to_extract_mesh": False, "use_marching_cubes": False, "use_vanilla_3dgs": False,
        }))[0]
    elif args.step == "refine":
        from sugar_trainers.refine import refined_training
        state["refined"] = refined_training(AttrDict({
            **common, "mesh_path": state["coarse_mesh"], "output_dir": None, "normal_consistency_factor": 0.1,
            "gaussians_per_triangle": args.gaussians_per_triangle, "n_vertices_in_fg": args.n_vertices,
            "refinement_iterations": args.refinement_iterations, "bboxmin": None, "bboxmax": None,
            "export_ply": True, "white_background": False,
        }))
    elif args.step == "texture":
        from sugar_extractors.refined_mesh import extract_mesh_and_texture_from_refined_sugar
        state["refined_mesh"] = extract_mesh_and_texture_from_refined_sugar(AttrDict({
            **common, "refined_model_path": state["refined"], "mesh_output_dir": None,
            "n_gaussians_per_surface_triangle": args.gaussians_per_triangle, "square_size": 8,
            "postprocess_mesh": False, "postprocess_density_threshold": 0.1, "postprocess_iterations": 5,
        }))

    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(state_path)


if __name__ == "__main__":
    main()
