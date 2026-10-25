"""Invocation-local summed-area acceleration for exact quarter-turn rectangles.

Only verified axis-aligned rectangles take this path. Everything else retains
closed-cell convex SAT. The tolerance/boundary contract is the same. This class
owns one immutable copy of a single observed mask; no cross-map cache exists.
"""
import math
import numpy as np
from collision import Snapshot as GenericSnapshot


class Snapshot(GenericSnapshot):
    def __init__(self, mask, res, origin=(0.,0.)):
        super().__init__(mask,res,origin)
        self._templates={}
        self._integral=None

    def collides(self, pose, footprint):
        try:
            x,y,yaw=map(float,pose)
            vertices=tuple(tuple(map(float,p)) for p in footprint)
        except (ValueError,TypeError):
            return super().collides(pose,footprint)
        if (yaw not in (0.,math.pi/2,math.pi,-math.pi/2)
                or not math.isfinite(x) or not math.isfinite(y)):
            return super().collides(pose,footprint)
        key=(yaw,vertices)
        if key not in self._templates:
            eligible=(len(vertices)==4 and all(len(p)==2 and all(math.isfinite(v) for v in p) for p in vertices))
            if eligible:
                xs={p[0] for p in vertices};ys={p[1] for p in vertices}
                eligible=(len(xs)==len(ys)==2 and len(set(vertices))==4
                          and all((a[0]==b[0]) != (a[1]==b[1]) for a,b in zip(vertices,vertices[1:]+vertices[:1])))
            if eligible:
                c,s=math.cos(yaw),math.sin(yaw)
                rotated=[(c*a-s*b,s*a+c*b) for a,b in vertices]
                self._templates[key]=(min(p[0] for p in rotated),min(p[1] for p in rotated),max(p[0] for p in rotated),max(p[1] for p in rotated))
            else:self._templates[key]=None
        template=self._templates[key]
        if template is None:return super().collides(pose,footprint)
        xlo,ylo,xhi,yhi=template
        xlo+=x;ylo+=y;xhi+=x;yhi+=y
        ox,oy=self.origin;h,w=self._mask.shape;r=self.res
        scale=max(1.,abs(xlo),abs(ylo),abs(xhi),abs(yhi),abs(ox),abs(oy),max(h,w)*r)
        tol=1e-12+64*np.finfo(float).eps*scale
        # Tiny/degenerate rectangles use general validation, not an unsafe shortcut.
        if xhi-xlo<=tol or yhi-ylo<=tol:return super().collides(pose,footprint)
        if xlo<=ox+tol or ylo<=oy+tol or xhi>=ox+w*r-tol or yhi>=oy+h*r-tol:return True
        # Lower tolerance expansion includes the cell immediately before an exact
        # lower boundary; upper expansion also absorbs division roundoff.
        x0=max(0,math.floor((xlo-tol-ox)/r));y0=max(0,math.floor((ylo-tol-oy)/r))
        x1=min(w-1,math.floor((xhi+tol-ox)/r));y1=min(h-1,math.floor((yhi+tol-oy)/r))
        if self._integral is None:
            a=self._mask.astype(np.int64).cumsum(axis=0).cumsum(axis=1)
            self._integral=np.pad(a,((1,0),(1,0)))
            self._integral.flags.writeable=False
        a=self._integral
        # Reject empty neighbor-expanded bounds cheaply. If an occupied cell
        # exists near a numerically ambiguous grid boundary, use the exact same
        # generic SAT predicate rather than inventing a second tolerance policy.
        bx0=max(0,x0-1);by0=max(0,y0-1);bx1=min(w-1,x1+1);by1=min(h-1,y1+1)
        nearby=a[by1+1,bx1+1]-a[by0,bx1+1]-a[by1+1,bx0]+a[by0,bx0]
        if not nearby:return False
        values=((xlo-ox)/r,(xhi-ox)/r,(ylo-oy)/r,(yhi-oy)/r)
        if any(abs(v-round(v))*r <= 4*tol for v in values):
            return super().collides(pose,footprint)
        return bool(a[y1+1,x1+1]-a[y0,x1+1]-a[y1+1,x0]+a[y0,x0])
