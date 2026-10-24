"""Read-only VM LaserScan shadow. No motion publisher, no manufacturer endpoints.
Native execution NOT_RUN; use ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=183.
"""
import os, math, json

def main():
 if os.environ.get('ROS_LOCALHOST_ONLY')!='1' or os.environ.get('ROS_DOMAIN_ID')!='183':
  raise RuntimeError('Explicit isolated VM ROS domain 183 required')
 import rclpy
 from rclpy.node import Node
 from sensor_msgs.msg import LaserScan
 from std_msgs.msg import String
 class Shadow(Node):
  def __init__(self):
   super().__init__('competition_vm_scan_shadow'); self.seq=0
   self.pub=self.create_publisher(String,'/competition_vm/scan_diagnostics',10)
   self.sub=self.create_subscription(LaserScan,'/competition_vm/scan',self.scan,10)
  def scan(self,msg):
   self.seq+=1
   payload={'schema_version':'0.1','producer_id':'vm_scan_shadow','producer_epoch':str(os.getpid()),'sequence':self.seq,'source_stamp_ns':str(msg.header.stamp.sec*10**9+msg.header.stamp.nanosec),'source_clock':'ROS_TIME','frame_id':msg.header.frame_id,'evidence_type':'NATIVE_ROS_SHADOW','config_hash':'unbound','valid_ranges':sum(math.isfinite(x) and msg.range_min<=x<=msg.range_max for x in msg.ranges),'control_enabled':False}
   out=String(); out.data=json.dumps(payload); self.pub.publish(out)
 rclpy.init(); node=Shadow()
 try:rclpy.spin(node)
 finally:node.destroy_node();rclpy.shutdown()
if __name__=='__main__': main()
