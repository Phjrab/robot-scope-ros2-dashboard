// C3 evaluation-only driver. Calls installed C++ classes; no Python reimplementation.
// Protected-member seam sets a small deterministic state, without replacing score/inCollision.
#include <chrono>
#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>
#include "nav2_smac_planner/collision_checker.hpp"
#include "nav2_smac_planner/node_lattice.hpp"
#include "nav2_mppi_controller/critics/cost_critic.hpp"
using json = nlohmann::json;

class ProbeCritic : public mppi::critics::CostCritic {
public:
  using CostCritic::inCollision;
  void prepare(std::shared_ptr<nav2_costmap_2d::Costmap2DROS> map) {
    costmap_ros_ = map; costmap_ = map->getCostmap();
    collision_checker_.setCostmap(costmap_);
    enabled_ = true; consider_footprint_ = true;
    possibly_inscribed_cost_ = circumscribed_cost_ = 82;
    circumscribed_radius_ = map->getLayeredCostmap()->getCircumscribedRadius();
    power_ = 1; weight_ = 1; critical_cost_ = 300; collision_cost_ = 1000000;
    near_goal_distance_ = .5;
  }
  bool scoreOne(float x, float y, float yaw) {
    mppi::models::State state; state.reset(1, 1);
    state.pose.pose.position.x=x; state.pose.pose.position.y=y;
    state.pose.pose.orientation.z=std::sin(yaw/2); state.pose.pose.orientation.w=std::cos(yaw/2);
    mppi::models::Trajectories traj; traj.reset(1, 1);
    traj.x(0,0)=x; traj.y(0,0)=y; traj.yaws(0,0)=yaw;
    mppi::models::Path path; path.reset(1); path.x(0)=x+2; path.y(0)=y;
    xt::xtensor<float,1> costs=xt::zeros<float>({1}); float dt=.05;
    mppi::CriticData data{state,traj,path,costs,dt,false,nullptr,nullptr,std::nullopt,std::nullopt};
    score(data); return data.fail_flag;
  }
};

int main(int argc, char **argv) {
  if(argc != 4) return 2;
  rclcpp::init(argc,argv);
  json inputs; std::ifstream(argv[1]) >> inputs;
  json result={{"mode",argv[3]},{"cases",json::array()}};
  bool fixed=std::string(argv[3])=="overlay", all=true, reproduced=false;
  auto node=std::make_shared<rclcpp_lifecycle::LifecycleNode>("c3_checker_probe");
  for(bool unknown: {false,true}) {
    auto ros=std::make_shared<nav2_costmap_2d::Costmap2DROS>(
      unknown?"c3_unknown":"c3_known","",unknown?"c3_unknown":"c3_known");
    ros->set_parameter(rclcpp::Parameter("plugins",std::vector<std::string>{}));
    ros->set_parameter(rclcpp::Parameter("footprint_padding",0.0));
    ros->set_parameter(rclcpp::Parameter("track_unknown_space",unknown));
    ros->on_configure(rclcpp_lifecycle::State());
    nav2_costmap_2d::Footprint footprint;
    for(auto xy: inputs["footprint"]) {
      geometry_msgs::msg::Point p; p.x=xy[0]; p.y=xy[1]; footprint.push_back(p);
    }
    ros->setRobotFootprint(footprint);
    auto map=ros->getCostmap();
    for(const auto &c: inputs["cases"]) {
      if(c.value("allow_unknown",false)!=unknown) continue;
      map->resizeMap(200,300,.02,0,0);
      map->resetMap(0,0,200,300);
      // Explicit raw byte assignments, including interior cells. Never invert occupancy.
      std::fill(map->getCharMap(),map->getCharMap()+60000,c.value("default_raw",0));
      if(c.contains("wall_columns")) for(int x:c["wall_columns"]) for(int y=0;y<300;y++) map->setCost(x,y,254);
      if(c.value("inflate_walls",false)) for(int ix=0;ix<200;ix++) {
        double d=1000;
        for(int wall:c["wall_columns"]) d=std::min(d,std::abs(ix-wall)*.02);
        const unsigned char raw=d==0?254:d<=.31?253:d<=.58?int(252*std::exp(-5*(d-.31))):0;
        for(int iy=0;iy<300;iy++) map->setCost(ix,iy,raw);
      }
      for(auto cell:c.value("raw_cells",json::array())) map->setCost(cell[0],cell[1],cell[2]);
      float x=c["pose"][0],y=c["pose"][1],yaw=c["pose"][2];
      unsigned int mx,my; float center=255;
      if(map->worldToMap(x,y,mx,my)) {
        if(!c.value("inflate_walls",false)) map->setCost(mx,my,c.value("center_raw",0));
        center=map->getCost(mx,my);
      }
      nav2_smac_planner::GridCollisionChecker smac(map,72,node);
      smac.setFootprint(footprint,false,82);
      ProbeCritic mppi; mppi.prepare(ros);
      auto begin=std::chrono::steady_clock::now();
      const float gx=x/.02f-.5f,gy=y/.02f-.5f,gb=yaw/(2*M_PI/72);
      bool sc=smac.inCollision(gx,gy,gb,unknown);
      bool mc=mppi.inCollision(center,x,y,yaw), ms=mppi.scoreOne(x,y,yaw);
      json row={{"id",c["id"]},{"center_raw",center},{"smac_collision",sc},
        {"mppi_direct_collision",mc},{"mppi_score_collision",ms},
        {"expected_collision",c["expected_collision"]}};
      row["stock_perimeter_cost_at_actual_pose"]=smac.footprintCostAtPose(x,y,yaw,footprint);
      row["smac_grid_input"]={gx,gy,gb};
      row["stock_smac_center_raw"]=map->getCost(unsigned(gx),unsigned(gy));
      const double sx=(unsigned(gx)+.5)*.02,sy=(unsigned(gy)+.5)*.02;
      const double st=smac.getPrecomputedAngles()[unsigned(gb)];
      row["stock_cached_pose"]={sx,sy,st};
      row["stock_perimeter_cost_at_cached_pose"]=smac.footprintCostAtPose(
        sx,sy,st,footprint);
      bool expected=c["expected_collision"];
      bool pass=sc==expected && mc==expected && ms==expected;
      if(c.contains("primitive")) {
        auto &table=nav2_smac_planner::NodeLattice::motion_table;
        table.lattice_metadata.grid_resolution=.02;
        table.lattice_metadata.heading_angles={0,float(M_PI/2)};
        table.num_angle_quantization=2;
        nav2_smac_planner::MotionPrimitive primitive;
        primitive.start_angle=0; primitive.end_angle=1;
        for(auto p:c["primitive"]) primitive.poses.emplace_back(p[0],p[1],p[2]);
        nav2_smac_planner::NodeLattice node_lattice(0);
        node_lattice.setPose({x/.02f-.5f,y/.02f-.5f,1});
        bool valid=node_lattice.isNodeValid(unknown,&smac,&primitive,false);
        row["lattice_primitive_valid"]=valid;
        pass=pass && !valid;
      }
      row["duration_us"]=std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-begin).count();
      row["regression_pass"]=pass;
      all=all&&pass; reproduced=reproduced||(!pass && expected);
      result["cases"].push_back(row);
    }
    ros->on_cleanup(rclcpp_lifecycle::State());
  }
  std::ifstream maps("/proc/self/maps"); std::string line;
  result["loaded_maps"]=json::array();
  while(std::getline(maps,line)) if(line.find(".so")!=std::string::npos) result["loaded_maps"].push_back(line);
  result["status"]=fixed?(all?"CHECKER_FIXED":"CHECKER_FAILED"):(reproduced?"CHECKER_REPRODUCED":"NOT_REPRODUCED");
  std::cout << result["status"] << "\n" << result["cases"].dump(2) << "\n";
  std::ofstream output(argv[2]); output << result.dump(2) << "\n";
  if(!output.good()) {std::cerr << "cannot persist checker packet\n"; return 3;}
  rclcpp::shutdown();
  return fixed?!all:!reproduced;
}
