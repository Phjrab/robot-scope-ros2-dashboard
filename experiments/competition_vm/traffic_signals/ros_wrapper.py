"""Optional isolated VM ROS 2 wrapper for prevalidated replay observations.
No Image subscription or camera owner. No Twist publisher. NOT RUN without rclpy.
"""
import json
import os
from core import StopGoFSM, StopInput

def main():
    if os.environ.get('ROS_LOCALHOST_ONLY')!='1' or os.environ.get('ROS_DOMAIN_ID')!='173':
        raise RuntimeError('VM-only wrapper requires ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=173')
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
    class ReplayNode(Node):
        def __init__(self):
            super().__init__('competition_traffic_vm_replay')
            self.fsm=StopGoFSM(simulation=True)
            self.pub=self.create_publisher(String,'/competition_vm/traffic_constraint',10)
            self.sub=self.create_subscription(String,'/competition_vm/traffic_input',self.receive,10)
            self.timer=self.create_timer(.05,self.watchdog)
            self.last=None
        def receive(self,msg):
            try:
                value=json.loads(msg.data)
                if not isinstance(value,dict):raise ValueError("object required")
                if value.get('command')=='begin':
                    if self.fsm.begin(**value['identity']):self.last=None
                    return
                i=StopInput(**value)
                # Never trust remote receipt timestamp: this is receiver local.
                from dataclasses import replace
                import time
                i=replace(i,receipt_s=time.monotonic())
                self.last=i
                self.pub.publish(String(data=json.dumps(self.fsm.update(i))))
            except (TypeError,ValueError,KeyError):
                import time
                self.fsm.state='INTERRUPTED';self.fsm.start=None
                result=self.fsm.update(self.last or StopInput(time.monotonic(),0))
                result['reason']='INVALID_MESSAGE';result['motion_constraint']['reason']='INVALID_MESSAGE'
                self.pub.publish(String(data=json.dumps(result)))
        def watchdog(self):
            import time
            if self.last is not None and time.monotonic()-self.last.receipt_s>.25:
                from dataclasses import replace
                expired=replace(self.last,receipt_s=time.monotonic(),observation_age_s=1.)
                self.pub.publish(String(data=json.dumps(self.fsm.update(expired))))
    rclpy.init();node=ReplayNode()
    try:rclpy.spin(node)
    finally:node.destroy_node();rclpy.shutdown()
if __name__=='__main__':main()
