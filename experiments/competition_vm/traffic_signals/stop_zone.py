"""Visual rectangle candidate extraction, NOT calibrated foot tracking.
Candidate geometry must be associated to the mission's known stop zone by integration.
"""
import cv2
import numpy as np

def rectangle_candidates(bgr,min_area=100):
    if bgr.dtype!=np.uint8 or bgr.ndim!=3 or bgr.shape[2]!=3:raise ValueError('bgr8 required')
    gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
    edge=cv2.Canny(gray,70,180)
    contours,_=cv2.findContours(edge,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    out=[]
    for c in contours:
        p=cv2.approxPolyDP(c,.03*cv2.arcLength(c,True),True)
        if len(p)==4 and cv2.isContourConvex(p) and cv2.contourArea(p)>=min_area:
            out.append({'polygon_image':p[:,0,:].tolist(),'status':'UNASSOCIATED_CANDIDATE','evidence_type':'IMAGE_GEOMETRY_ONLY'})
    return out

def feet_membership(polygon,points,*,evidence_kind):
    if evidence_kind not in ('SIM_GT','KINEMATIC','VISUAL','PROXY'):raise ValueError('unknown evidence type')
    poly=np.asarray(polygon,dtype=np.float32)
    if poly.ndim!=2 or poly.shape[1]!=2 or len(poly)<3 or not np.isfinite(poly).all() or abs(cv2.contourArea(poly))<1e-8:
        raise ValueError('valid finite polygon required')
    if len(points)!=2:raise ValueError('two front feet required')
    inside=[]
    for point in points:
        if point is None or len(point)!=2 or not np.isfinite(point).all():inside.append(False)
        else:inside.append(cv2.pointPolygonTest(poly,tuple(map(float,point)),False)>=0)
    return {'front_left_status':'INSIDE' if inside[0] else 'UNPROVEN',
            'front_right_status':'INSIDE' if inside[1] else 'UNPROVEN',
            'feet_evidence_kind':evidence_kind,'both_inside':all(inside),
            'qualified':False}
