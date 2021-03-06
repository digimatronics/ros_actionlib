#! /usr/bin/env python
# Copyright (c) 2009, Willow Garage, Inc.
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the Willow Garage, Inc. nor the names of its
#       contributors may be used to endorse or promote products derived from
#       this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

# Author: Stuart Glaser

import roslib; roslib.load_manifest('actionlib')
import threading
import time
import rospy
from roslib.msg import Header
from actionlib_msgs.msg import *
from action_client import ActionClient, CommState, get_name_of_constant

class SimpleGoalState:
    PENDING = 0
    ACTIVE = 1
    DONE = 2
SimpleGoalState.to_string = classmethod(get_name_of_constant)


class SimpleActionClient:
    ## @brief Constructs a SimpleActionClient and opens connections to an ActionServer.
    ##
    ## @param ns The namespace in which to access the action.  For
    ## example, the "goal" topic should occur under ns/goal
    ##
    ## @param ActionSpec The *Action message type.  The SimpleActionClient
    ## will grab the other message types from this type.
    def __init__(self, ns, ActionSpec):
        self.action_client = ActionClient(ns, ActionSpec)
        self.simple_state = SimpleGoalState.DONE
        self.gh = None
        self.done_condition = threading.Condition()

        
    ## @brief [Deprecated] Use wait_for_server
    def wait_for_action_server_to_start(self, timeout = rospy.Duration()):
        return self.wait_for_server(timeout)

    ## @brief Blocks until the action server connects to this client
    ##
    ## @param timeout Max time to block before returning. A zero
    ## timeout is interpreted as an infinite timeout.
    ##
    ## @return True if the server connected in the allocated time. False on timeout
    def wait_for_server(self, timeout = rospy.Duration()):
        return self.action_client.wait_for_server(timeout)


    ## @brief Sends a goal to the ActionServer, and also registers callbacks
    ## 
    ## If a previous goal is already active when this is called. We simply forget
    ## about that goal and start tracking the new goal. No cancel requests are made.
    ##
    ## @param done_cb Callback that gets called on transitions to
    ## Done.  The callback should take two parameters: the terminal
    ## state (as an integer from actionlib_msgs/GoalStatus) and the
    ## result.
    ##
    ## @param active_cb   No-parameter callback that gets called on transitions to Active.
    ##
    ## @param feedback_cb Callback that gets called whenever feedback
    ## for this goal is received.  Takes one parameter: the feedback.
    def send_goal(self, goal, done_cb = None, active_cb = None, feedback_cb = None):
        # destroys the old goal handle
        self.stop_tracking_goal()

        self.done_cb = done_cb
        self.active_cb = active_cb
        self.feedback_cb = feedback_cb

        self.simple_state = SimpleGoalState.PENDING
        self.gh = self.action_client.send_goal(goal, self._handle_transition, self._handle_feedback)

    
    ## @brief [Deprecated] Use wait_for_result
    def wait_for_goal_to_finish(self, timeout = rospy.Duration()):
        return self.wait_for_result(timeout)

    ## @brief Blocks until this goal transitions to done
    ## @param timeout Max time to block before returning. A zero timeout is interpreted as an infinite timeout.
    ## @return True if the goal finished. False if the goal didn't finish within the allocated timeout
    def wait_for_result(self, timeout = rospy.Duration()):
        if not self.gh:
            rospy.logerr("Called wait_for_goal_to_finish when no goal exists")
            return False

        timeout_time = rospy.get_rostime() + timeout
        loop_period = rospy.Duration(0.1)
        self.done_condition.acquire()
        while not rospy.is_shutdown():
            time_left = timeout_time - rospy.get_rostime()
            if timeout > rospy.Duration(0.0) and time_left <= rospy.Duration(0.0):
                break

            if self.simple_state == SimpleGoalState.DONE:
                break

            if time_left > loop_period:
                time_left = loop_period

            self.done_condition.wait(time_left.to_seconds())
        self.done_condition.release()

        return self.simple_state == SimpleGoalState.DONE


    ## @brief [Deprecated] Gets the current state of the goal: [PENDING], [ACTIVE], or [DONE]
    ##
    ## Deprecated.  Use get_state instead
    def get_goal_state(self):
        rospy.logwarn("SimpleActionClient.get_goal_state has been deprecated")
        if not self.gh:
            rospy.logerr("Called get_goal_state when no goal is running")
            return SimpleGoalState.DONE

        comm_state = self.gh.get_comm_state()
        if comm_state in [CommState.WAITING_FOR_GOAL_ACK, CommState.PENDING, CommState.RECALLING]:
            return SimpleGoalState.PENDING
        elif comm_state in [CommState.ACTIVE, CommState.PREEMPTING]:
            return SimpleGoalState.ACTIVE
        elif comm_state in [CommState.DONE]:
            return SimpleGoalState.DONE
        elif comm_state in [CommState.WAITING_FOR_RESULT, CommState.WAITING_FOR_CANCEL_ACK]:
            return self.simple_state

        rospy.logerr("Error trying to interpret CommState in get_goal_state: %i" % comm_state)
        return SimpleGoalState.DONE


    ## @brief Gets the Result of the current goal
    def get_result(self):
        if not self.gh:
            rospy.logerr("Called get_result when no goal is running")
            return None

        return self.gh.get_result()


    ## @brief [Deprecated] Get the terminal state information for this goal
    ##
    ## Deprecated.  Use get_state instead.
    ## 
    ## Possible States Are: RECALLED, REJECTED, PREEMPTED, ABORTED,
    ## SUCCEEDED, LOST.  This call only makes sense if
    ## SimpleGoalState==DONE. This will sends ROS_WARNs if we're not
    ## in DONE
    ##
    ## @return The terminal state
    def get_terminal_state(self):
        rospy.logwarn("SimpleactionClient.get_terminal_state has been deprecated")
        if not self.gh:
            rospy.logerr("Called get_terminal_state when no goal is running")
            return GoalStatus.LOST
        return self.gh.get_terminal_state()

    
    ## @brief Get the state information for this goal
    ##
    ## Possible States Are: PENDING, ACTIVE, RECALLED, REJECTED,
    ## PREEMPTED, ABORTED, SUCCEEDED, LOST.
    ##
    ## @return The goal's state. Returns LOST if this
    ## SimpleActionClient isn't tracking a goal.
    def get_state(self):
        if not self.gh:
            rospy.logerr("Called get_state when no goal is running")
            return GoalStatus.LOST
        status = gh.get_goal_status()
        
        if status == GoalStatus.RECALLING:
            status = GoalStatus.PENDING
        elif status == GoalStatus.PREEMPTING:
            status = GoalStatus.ACTIVE

        return status



    ## @brief Cancels all goals currently running on the action server
    ## 
    ## This preempts all goals running on the action server at the point that
    ## this message is serviced by the ActionServer.
    def cancel_all_goals(self):
        self.action_client.cancel_all_goals()

    
    ## @brief Cancels the goal that we are currently pursuing
    def cancel_goal(self):
        if self.gh:
            self.gh.cancel()


    ## @brief Stops tracking the state of the current goal. Unregisters this goal's callbacks
    ## 
    ## This is useful if we want to make sure we stop calling our callbacks before sending a new goal.
    ## Note that this does not cancel the goal, it simply stops looking for status info about this goal.
    def stop_tracking_goal(self):
        del self.gh
        self.gh = None

    def _handle_transition(self, gh):
        comm_state = self.gh.get_comm_state()

        error_msg = "Received comm state %s when in simple state %s" % \
            (CommState.to_string(comm_state), SimpleGoalState.to_string(self.simple_state))

        if comm_state == CommState.ACTIVE:
            if self.simple_state == SimpleGoalState.PENDING:
                self._set_simple_state(SimpleGoalState.ACTIVE)
                if self.active_cb:
                    self.active_cb()
            elif self.simple_state == SimpleGoalState.DONE:
                rospy.logerr(error_msg)
        elif comm_state == CommState.RECALLING:
            if self.simple_state != SimpleGoalState.PENDING:
                rospy.logerr(error_msg)
        elif comm_state == CommState.PREEMPTING:
            if self.simple_state == SimpleGoalState.PENDING:
                self._set_simple_state(SimpleGoalState.ACTIVE)
                if self.active_cb:
                    self.active_cb()
            elif self.simple_state == SimpleGoalState.DONE:
                rospy.logerr(error_msg)
        elif comm_state == CommState.DONE:
            if self.simple_state in [SimpleGoalState.PENDING, SimpleGoalState.ACTIVE]:
                self._set_simple_state(SimpleGoalState.DONE)
                if self.done_cb:
                    self.done_cb(self.gh.get_goal_status(), self.gh.get_result())
                self.done_condition.acquire()
                self.done_condition.notifyAll()
                self.done_condition.release()
            elif self.simple_state == SimpleGoalState.DONE:
                rospy.logerr("SimpleActionClient received DONE twice")

    def _handle_feedback(self, gh, feedback):
        if gh != self.gh:
            rospy.logerr("Got a feedback callback on a goal handle that we're not tracking. %s vs %s" % (self.gh.comm_state_machine.action_goal.goal_id.id, gh.comm_state_machine.action_goal.goal_id.id))
            return
        if self.feedback_cb:
            self.feedback_cb(feedback)


    def _set_simple_state(self, state):
        self.simple_state = state
