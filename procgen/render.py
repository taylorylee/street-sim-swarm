"""Axonometric preview render (no GPU needed). Painter's algorithm over baked face colors."""
from __future__ import annotations

import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PolyCollection

from .palette import PALETTE, rgb01


def render_axo(mesh, out_png, azimuth=-38, elevation=42, size=(12, 12), dpi=160):
    az, el = math.radians(azimuth), -math.radians(90 - elevation)
    rz = np.array([[math.cos(az), -math.sin(az), 0], [math.sin(az), math.cos(az), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, math.cos(el), -math.sin(el)], [0, math.sin(el), math.cos(el)]])
    R = rx @ rz
    v = mesh.vertices @ R.T
    tri = v[mesh.faces]
    # back-face cull: keep faces whose normal points toward the viewer (+z after rotation)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    keep = n[:, 2] > 1e-9
    tri, cols = tri[keep], mesh.visual.face_colors[keep][:, :3] / 255
    # flat ground layers (ground, streets, parks) always paint first; then far-to-near
    world_z = mesh.vertices[mesh.faces[keep]][:, :, 2].max(1)
    depth = tri[:, :, 2].mean(1)
    tall = world_z > 0.2
    order = np.lexsort((depth, np.where(tall, 0, world_z), tall))
    fig = plt.figure(figsize=size, dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    fig.patch.set_facecolor(rgb01(PALETTE["ground"]))
    ax.set_facecolor(rgb01(PALETTE["ground"]))
    pc = PolyCollection(tri[order][:, :, :2], facecolors=cols[order],
                        edgecolors=cols[order], linewidths=0.25, antialiased=True)
    ax.add_collection(pc)
    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(out_png, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    return out_png
