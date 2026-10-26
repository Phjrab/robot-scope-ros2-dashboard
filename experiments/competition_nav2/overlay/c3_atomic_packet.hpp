// Opt-in bounded diagnostic of the costmap held by Smac's createPlan mutex.
// Does not publish, alter costs, change checker decisions or feed planner inputs.
#pragma once
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>
#include "nlohmann/json.hpp"

namespace c3_atomic {
using Json = nlohmann::json;
inline int64_t steady_ns() {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
}
template<class Pose> Json pose(const Pose &p) {
  return {{"position", {p.position.x,p.position.y,p.position.z}},
          {"quaternion", {p.orientation.x,p.orientation.y,p.orientation.z,p.orientation.w}}};
}
template<class Body> Json footprint(const Body &body) {
  Json result=Json::array();
  for(const auto &p:body) result.push_back({p.x,p.y});
  return result;
}
template<class Map> class Packet {
  Map *map_;
  std::string base_;
  std::vector<unsigned char> bytes_;
  Json j_;
  bool written_=false;
public:
  template<class Body,class Pose> Packet(Map *map,const Body &body,
      const Pose &start,const Pose &goal,int64_t ros_ns,const std::string &frame,
      bool allow_unknown) : map_(map) {
    const char *dir=std::getenv("C3_ATOMIC_DIR");
    if(!dir || !*dir) return;
    static unsigned invocation=0;
    const unsigned id=++invocation;
    if(id>64) throw std::runtime_error("C3 atomic packet invocation bound exceeded");
    std::filesystem::create_directories(dir);
    base_=std::string(dir)+"/plan-"+std::to_string(id);
    const auto size=map->getSizeInCellsX()*size_t(map->getSizeInCellsY());
    if(size>1024*1024) throw std::runtime_error("C3 atomic packet grid bound exceeded");
    const auto begin=steady_ns();
    bytes_.assign(map->getCharMap(),map->getCharMap()+size);
    const char *source=std::getenv("C3_SOURCE_SHA"), *image=std::getenv("C3_IMAGE_ID");
    j_={{"schema","c3-planner-atomic.v1"},{"invocation",id},
        {"process_epoch_steady_ns",epoch()},{"source_sha",source?source:""},
        {"image_id",image?image:""},{"frame",frame},{"clock","ROS simulation clock"},
        {"lock_capture_ros_ns",ros_ns},{"capture_steady_ns",begin},
        {"raw_costmap_update_stamp",nullptr},
        {"stamp_limit","Costmap2D has no update header; capture time is not sensor/update time"},
        {"width",map->getSizeInCellsX()},{"height",map->getSizeInCellsY()},
        {"resolution",map->getResolution()},{"origin",{map->getOriginX(),map->getOriginY()}},
        {"raw_file","plan-"+std::to_string(id)+".bin"},{"raw_bytes",size},
        {"footprint",footprint(body)},{"allow_unknown",allow_unknown},
        {"start",pose(start)},{"goal",pose(goal)},{"path",Json::array()},
        {"segments",Json::array()},{"returned_valid_path",false},
        {"lock_scope","SmacPlannerLattice::createPlan Costmap2D mutex; snapshot before search through return"}};
  }
  static int64_t epoch() {static const auto value=steady_ns();return value;}
  template<class Plan> void plan(const Plan &p) {
    if(base_.empty()) return;
    j_["path_header_ros_ns"]=int64_t(p.header.stamp.sec)*1000000000+p.header.stamp.nanosec;
    for(const auto &q:p.poses) j_["path"].push_back(pose(q.pose));
  }
  template<class Body> void segment(int index,const Body &body,
      double ax,double ay,double at,double bx,double by,double bt,bool collision) {
    if(base_.empty()) return;
    j_["segments"].push_back({{"index",index},{"a",{ax,ay,at}},{"b",{bx,by,bt}},
      {"footprint",footprint(body)},{"actual_supplemental_checker_collision",collision}});
  }
  void finish(bool returned,int64_t ros_ns) {
    if(base_.empty() || written_) return;
    j_["returned_valid_path"]=returned;
    j_["finish_ros_ns"]=ros_ns;
    j_["raw_unchanged_under_lock"]=std::equal(bytes_.begin(),bytes_.end(),map_->getCharMap());
    std::ofstream raw(base_+".bin",std::ios::binary);
    raw.write(reinterpret_cast<const char*>(bytes_.data()),bytes_.size());raw.close();
    if(!raw) throw std::runtime_error("C3 atomic raw write failed");
    j_["finish_steady_ns"]=steady_ns();
    j_["capture_to_finish_ns"]=int64_t(j_["finish_steady_ns"])-int64_t(j_["capture_steady_ns"]);
    std::ofstream out(base_+".json");out<<j_.dump()<<'\n';out.close();
    if(!out) throw std::runtime_error("C3 atomic metadata write failed");
    written_=true;
  }
};
} // namespace c3_atomic
