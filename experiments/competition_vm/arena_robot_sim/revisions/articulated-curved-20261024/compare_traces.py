"""Compare actual saved planar trajectories, never synthesize a planning result."""
import argparse,json,hashlib,math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont

def metrics(p):
 d=json.loads(p.read_text()); a=np.array([[f['t'],*f['pose']] for f in d['frames']]);dt=np.diff(a[:,0]);v=np.diff(a[:,1:3],axis=0)/dt[:,None];yaw=np.unwrap(a[:,3]);w=np.diff(yaw)/dt;acc=np.diff(v,axis=0)/((dt[1:]+dt[:-1])/2)[:,None]
 return d,a,{'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'stored_metrics':d['metrics'],'stored_span_s':float(a[-1,0]-a[0,0]),'path_length_m':float(np.linalg.norm(np.diff(a[:,1:3],axis=0),axis=1).sum()),'yaw_range_deg':np.degrees([yaw.min(),yaw.max()]).tolist(),'peak_yaw_rate_rad_s':float(np.abs(w).max()),'peak_planar_speed_m_s':float(np.linalg.norm(v,axis=1).max()),'peak_finite_difference_acceleration_m_s2':float(np.linalg.norm(acc,axis=1).max()) if len(acc) else 0}

def main():
 p=argparse.ArgumentParser();p.add_argument('before',type=Path);p.add_argument('after',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--open-diagnostic',action='store_true');args=p.parse_args();args.output.mkdir(exist_ok=True,parents=True)
 data=[metrics(args.before),metrics(args.after)];assert data[0][0]['scene']['cones']==data[1][0]['scene']['cones'], 'Scenario cone geometry differs';assert data[0][0]['scene']['footprint']==data[1][0]['scene']['footprint'], 'Planner footprint differs';(args.output/'comparison.json').write_text(json.dumps({'before':data[0][2],'after':data[1][2],'limits':['Finite differences of stored planar poses, not measured actuator response','No physics, balance, contact-force or hardware validation']},indent=2))
 im=Image.new('RGB',(1000,850),(18,25,34));dr=ImageDraw.Draw(im);font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',19);small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',15)
 dr.text((25,15),('OPEN DIAGNOSTIC LAYOUT | NOT ORIGINAL TIGHT LAYOUT' if args.open_diagnostic else 'ACTUAL RECORDED TRACES | SYNTHETIC PLANAR, NOT DYNAMICS'),font=font,fill='white')
 for n,(d,a,m) in enumerate(data):
  ox=30+500*n
  def xy(x,y):return (ox+40+x*130,730-(y-.5)*130)
  dr.text((ox,50),'BEFORE: fixed yaw' if n==0 else 'AFTER: gradual yaw',font=font,fill='white')
  for poly in d['scene']['allowed_floor_polygons'].values():dr.polygon([xy(*v) for v in poly],fill=(40,66,73),outline=(160,180,185))
  for c in d['scene']['cones']:
   x,y=c['xy'];h=c['base_side_m']/2;dr.rectangle([xy(x-h,y+h),xy(x+h,y-h)],fill=(250,113,27))
  dr.line([xy(*r[1:3]) for r in a],fill=(240,210,70),width=3)
  for row in a[::max(1,len(a)//22)]:
   _,x,y,yaw=row;dr.line([xy(x,y),xy(x+.14*math.cos(yaw),y+.14*math.sin(yaw))],fill=(130,220,255),width=2)
  dr.text((ox+255,100),f"Span: {m['stored_span_s']:.2f} s\nPath: {m['path_length_m']:.3f} m\nMax yaw rate:\n{m['peak_yaw_rate_rad_s']:.3f} rad/s\nMax speed:\n{m['peak_planar_speed_m_s']:.3f} m/s",font=small,fill='white',spacing=9)
 dr.text((25,785),'Yellow: recorded center trajectory. Cyan ticks: recorded body heading.',font=font,fill='white');dr.text((25,815),'Same obstacles in both panels. Kinematic / synthetic planar, NOT dynamics.',font=small,fill=(230,196,125));im.save(args.output/'comparison.png')
if __name__=='__main__':main()
