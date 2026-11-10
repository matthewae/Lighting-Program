# 3D models in MiniDesk

Every fixture type has a **3D model** that is only used for the look in the stage view.
Channels, DMX addresses and everything else still come from the fixture profile / the console
file.

## Built-in models (made for MiniDesk, free to use)

Chosen automatically from the fixture name; change it in **Patch → Edit fixture type & 3D model**.

| Model | Used for (in GMS_MATT.SHO) |
|---|---|
| `beam` – moving head beam | CM-280V2@16 |
| `hybrid` – beam/spot/wash moving head | AS_BSW350 |
| `spot`, `wash` | other moving heads |
| `par` – LED PAR can | CLED-543, PAR NEW, PAR Trial |
| `strobe` – strobe bar | STROBE 2.5 |
| `fresnel` – fresnel with barn doors | Fresnell |
| `hazer` | HAZER |
| `fog_vertical` – vertical fog with LED ring | DSK-1500VS |
| `fog` | DF-3000S |
| `ledbar`, `blinder`, `generic` | – |

The same models are in [`minidesk/models/`](../minidesk/models) as `.obj` files – open them in
Blender to see the expected structure, or use them as a starting point for your own models.
Trusses / towers are generated automatically from the fixture positions.

## Your own models

**Patch → Edit fixture type & 3D model → Import model file…**

| Format | Notes |
|---|---|
| **OBJ** (+ `.mtl`) | recommended; materials give the colours |
| **GLB / glTF 2.0** | node names give the parts, Y-up is converted automatically |
| **STL** | one colour, no parts |

Other formats (3DS, FBX, SKP, DAE, DWG): import them in Blender and export OBJ or GLB.

Conventions:

* **Z up**, the model stands on the floor; the light leaves the head along **+Z** (pointing up).
  Hanging fixtures are turned upside down automatically.
* Units do not matter: imported models are fitted to a typical size for the fixture kind
  (e.g. 0.55 m for a beam) – adjust with *Model scale*.
* Parts (OBJ `o`/`g` names, glTF node names): `base` (fixed), `yoke` (turns with pan),
  `head` (pan + tilt). A model without `head` turns as a whole (fine for PARs, strobes…).
* Materials named `lens`, `led`, `emit`, `light`, `glass` or with an emissive colour glow with the
  DMX colour/intensity.
* Optional tilt pivot: a comment line `# minidesk pivot x y z` in the OBJ (otherwise the centre of
  the `head` part).
* Keep it light: under ~2 000 polygons per fixture (use Blender's *Decimate* modifier).
  Textures are not shown.

Imported files are copied to `~/.minidesk/models/` so the show keeps working when the original
file is moved.
