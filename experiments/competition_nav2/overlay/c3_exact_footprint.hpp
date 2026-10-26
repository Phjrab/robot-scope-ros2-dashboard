// C3 isolated experiment, not an installed Nav2 replacement.
// Convex full-polygon/closed-cell SAT including interior cells. No extra padding.
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>

namespace c3_exact {
struct Point {double x, y;};
struct Axis {double x, y, lo, hi;};

template<class Map, class Footprint>
bool collision(Map *map, const Footprint &body, double x, double y, double yaw,
               bool allow_unknown) {
  constexpr double eps=1e-10;
  if(!map || body.size()<3 || body.size()>32 || !std::isfinite(x) ||
     !std::isfinite(y) || !std::isfinite(yaw)) return true;
  const double r=map->getResolution(), ox=map->getOriginX(), oy=map->getOriginY();
  if(!(r>0) || !std::isfinite(r)) return true;
  std::array<Point,32> points;
  std::array<Axis,32> axes;
  const auto n=body.size(); const double c=std::cos(yaw),s=std::sin(yaw);
  double minx=INFINITY,miny=INFINITY,maxx=-INFINITY,maxy=-INFINITY;
  double turn=0;
  for(size_t i=0;i<n;i++) {
    if(!std::isfinite(body[i].x)||!std::isfinite(body[i].y)) return true;
    points[i]={x+c*body[i].x-s*body[i].y,y+s*body[i].x+c*body[i].y};
    minx=std::min(minx,points[i].x);maxx=std::max(maxx,points[i].x);
    miny=std::min(miny,points[i].y);maxy=std::max(maxy,points[i].y);
  }
  // Map exterior is always blocked, independently of the unknown-cell policy.
  if(minx<=ox || miny<=oy || maxx>=ox+r*map->getSizeInCellsX() ||
     maxy>=oy+r*map->getSizeInCellsY()) return true;
  for(size_t i=0;i<n;i++) {
    const auto a=points[i],b=points[(i+1)%n],d=points[(i+2)%n];
    const double cross=(b.x-a.x)*(d.y-b.y)-(b.y-a.y)*(d.x-b.x);
    if(std::abs(cross)>eps) {if(turn*cross<0) return true;turn=cross;}
    axes[i]={-(b.y-a.y),b.x-a.x,INFINITY,-INFINITY};
    if(std::hypot(axes[i].x,axes[i].y)<eps) return true;
    for(size_t j=0;j<n;j++) {
      const double p=axes[i].x*points[j].x+axes[i].y*points[j].y;
      axes[i].lo=std::min(axes[i].lo,p);axes[i].hi=std::max(axes[i].hi,p);
    }
  }
  if(std::abs(turn)<eps) return true;
  // Include the cell to the left/below an exact grid-line contact.
  const int x0=std::max(0,int(std::floor((minx-ox)/r))-1);
  const int y0=std::max(0,int(std::floor((miny-oy)/r))-1);
  const int x1=std::min(int(map->getSizeInCellsX())-1,int(std::floor((maxx-ox)/r)));
  const int y1=std::min(int(map->getSizeInCellsY())-1,int(std::floor((maxy-oy)/r)));
  for(int iy=y0;iy<=y1;iy++) for(int ix=x0;ix<=x1;ix++) {
    const auto raw=map->getCost(ix,iy);
    if(raw!=254 && !(raw==255 && !allow_unknown)) continue;
    const double cx=ox+(ix+.5)*r,cy=oy+(iy+.5)*r,h=r/2;
    if(cx+h<minx-eps || cx-h>maxx+eps || cy+h<miny-eps || cy-h>maxy+eps) continue;
    bool overlap=true;
    for(size_t i=0;i<n;i++) {
      const auto &a=axes[i];const double p=a.x*cx+a.y*cy;
      const double extent=h*(std::abs(a.x)+std::abs(a.y));
      if(p+extent<a.lo-eps || p-extent>a.hi+eps) {overlap=false;break;}
    }
    if(overlap) return true;
  }
  return false;
}

template<class Map,class Footprint>
bool sweep(Map *map,const Footprint &body,double ax,double ay,double at,
           double bx,double by,double bt,bool allow_unknown) {
  if(!std::isfinite(ax)||!std::isfinite(ay)||!std::isfinite(at)||
     !std::isfinite(bx)||!std::isfinite(by)||!std::isfinite(bt)) return true;
  double radius=0;
  for(const auto &p:body) radius=std::max(radius,std::hypot(p.x,p.y));
  const double da=std::atan2(std::sin(bt-at),std::cos(bt-at));
  // <=1/10 cell corner displacement and <=.005rad: .002m at the fixed .02 grid.
  // Bounded numerical sweep, NOT a mathematical proof of continuous clearance.
  const double step=map->getResolution()/10;
  if(!(step>0)) return true;
  const double count=std::max({1.,std::ceil((std::hypot(bx-ax,by-ay)+radius*std::abs(da))/step),
                              std::ceil(std::abs(da)/.005)});
  if(!std::isfinite(count) || count>4096) return true;
  for(int i=0;i<=int(count);i++) {
    const double u=i/count;
    if(collision(map,body,ax+u*(bx-ax),ay+u*(by-ay),at+u*da,allow_unknown)) return true;
  }
  return false;
}
}  // namespace c3_exact
