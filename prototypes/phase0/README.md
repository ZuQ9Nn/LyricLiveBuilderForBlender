# Phase 0 prototypes

Throwaway scripts used to settle the open technical questions before the real implementation.
Results: [docs/05_prototype_results.md](../../docs/05_prototype_results.md).

| File | Item | Runs in |
|---|---|---|
| `fontinfo_proto.py` | S0-01 sfnt metrics reader (TTF/OTF/TTC) | any Python |
| `s0_01_glyph_metrics.py` | S0-01 Blender text size vs font em | Blender |
| `s0_02_bake_speed.py` | S0-02 bulk keyframe writing into layered actions | Blender |
| `convert_proto.py`, `s0_03_axis_export.py` | S0-03 Blender → Unity conversion and LLBM mesh writer | Blender |
| `unity_locate_proto.py` | S0-04 Unity editor lookup, project lock check, batch launch | Blender (Windows) |
| `s0_08_tap_latency.py` | S0-08 tap latency measurement (sidebar tab "LLB試作") | Blender UI |
| `s0_09_retopo.py` | S0-09 text retopology parameter grid | Blender |
| `s0_10_asset_tags.py` | S0-10 asset tag indexing | Blender |
| `build_check_blend.py` | builds `tests/manual/check_phase0.blend` | Blender |
| `unity/Editor/*.cs` | S0-03/S0-04 mesh reader, batch entry, auto build | Unity Editor |
| `unity/Shaders/*.shader` | S0-07 unlit and dome shaders | Unity |
| `unity/S0-11/LLBProtoSync.cs` | S0-11 UdonSharp playback sync | Unity (UdonSharp) |

Background run example (from the repository root):

```
blender --background --factory-startup --python prototypes/phase0/build_check_blend.py
```

The scripts reference Windows system fonts (`C:\Windows\Fonts\...`) for local testing only;
no font files are part of this repository.
