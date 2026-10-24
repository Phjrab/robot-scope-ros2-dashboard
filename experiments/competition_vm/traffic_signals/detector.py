"""Explicit local model adapter. No model downloads, torch.hub, or fallback weights."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import importlib.metadata
import math

@dataclass(frozen=True)
class Detection:
    bbox: tuple
    confidence: float
    class_id: int
    track_id: str

def iou(a,b):
    ix=max(0.,min(a[2],b[2])-max(a[0],b[0]));iy=max(0.,min(a[3],b[3])-max(a[1],b[1]))
    inter=ix*iy;area=lambda x:max(0.,x[2]-x[0])*max(0.,x[3]-x[1])
    return inter/max(1e-9,area(a)+area(b)-inter)

class Association:
    """Expected image ROI must be calibrated for this crossing/heading externally.
    Ambiguous candidates fail closed; largest-box fallback is intentionally absent."""
    def __init__(self, min_iou=.2, ambiguity_margin=.15):
        self.min_iou=min_iou;self.margin=ambiguity_margin;self.last=None;self.identity=None
    def select(self,detections,expected_roi,identity):
        if identity!=self.identity:self.last=None;self.identity=identity
        if expected_roi is None:return None,'ASSOCIATION_UNCERTAIN'
        ranked=sorted(((iou(d.bbox,expected_roi),d) for d in detections),key=lambda x:x[0],reverse=True)
        if not ranked or ranked[0][0]<self.min_iou:return None,'DETECTOR_MISSING'
        if len(ranked)>1 and ranked[0][0]-ranked[1][0]<self.margin:return None,'ASSOCIATION_UNCERTAIN'
        chosen=ranked[0][1]
        if self.last is not None and iou(chosen.bbox,self.last.bbox)<.1:
            self.last=chosen;return None,'TRACK_RESET'
        self.last=chosen;return chosen,None

class LocalUltralytics:
    def __init__(self, weights, *, expected_sha256, trusted_pickle=False, package_version=None,
                 family='ultralytics', allowed_classes=()):
        path=Path(weights).resolve()
        if not path.is_file(): raise FileNotFoundError('INPUT_REQUIRED: owner weights missing')
        if path.suffix.lower() not in ('.pt','.onnx'):raise ValueError('only explicit pt/onnx artifacts')
        self.sha256=hashlib.sha256(path.read_bytes()).hexdigest()
        if self.sha256!=expected_sha256:raise ValueError('model checksum mismatch')
        if family!='ultralytics':raise ValueError('INPUT_REQUIRED: provide tested YOLOv5 loader/version; not interchangeable')
        if path.suffix.lower()=='.pt' and not trusted_pickle:
            raise ValueError('untrusted pickle model refused; owner provenance required')
        if not package_version:raise ValueError('training-compatible pinned loader version required')
        if importlib.metadata.version('ultralytics')!=package_version:raise ValueError('loader version mismatch')
        if not allowed_classes:raise ValueError('class IDs required from owner metadata')
        from ultralytics import YOLO
        self.model=YOLO(str(path),task='detect');self.allowed=set(allowed_classes)
        self.version=package_version
    def infer(self,bgr):
        # Ultralytics predict returns native original-image xyxy coordinates;
        # do not inverse-letterbox these a second time.
        r=self.model.predict(source=bgr,device='cpu',verbose=False)[0]
        result=[]
        for idx,(box,conf,cls) in enumerate(zip(r.boxes.xyxy.tolist(),r.boxes.conf.tolist(),r.boxes.cls.tolist())):
            if int(cls) in self.allowed and all(math.isfinite(x) for x in box+[conf]):
                result.append(Detection(tuple(box),float(conf),int(cls),f'detection-{idx}'))
        return result
