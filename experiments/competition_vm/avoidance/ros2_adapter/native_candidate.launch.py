"""NOT_RUN candidate launch. Requires a separately provided VM map/TF/odom/scan plant.
Never includes robot drivers, SDK, a bridge, or production service launch files.
"""
import os
from pathlib import Path

def generate_launch_description():
 if os.environ.get('ROS_LOCALHOST_ONLY')!='1' or os.environ.get('ROS_DOMAIN_ID')!='183':
  raise RuntimeError('Set ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=183 for isolated VM only')
 from launch import LaunchDescription
 from launch.actions import DeclareLaunchArgument
 from launch.substitutions import LaunchConfiguration
 from launch_ros.actions import Node
 default=str(Path(__file__).resolve().parents[1]/'config/rpp_circle_vm_candidate.yaml')
 params=LaunchConfiguration('params')
 return LaunchDescription([
  DeclareLaunchArgument('params',default_value=default),
  Node(package='nav2_planner',executable='planner_server',name='planner_server',parameters=[params],output='screen'),
  Node(package='nav2_controller',executable='controller_server',name='controller_server',parameters=[params],remappings=[('cmd_vel','/competition_vm/cmd_vel_untrusted')],output='screen'),
  Node(package='nav2_lifecycle_manager',executable='lifecycle_manager',name='vm_lifecycle',parameters=[{'use_sim_time':True,'autostart':False,'node_names':['planner_server','controller_server']}],output='screen'),
 ])
