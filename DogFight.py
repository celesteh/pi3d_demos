#!/usr/bin/python
from __future__ import absolute_import, division, print_function, unicode_literals
"""quite a complicated demo showing many features of pi3d as well as
communication between players using httpRequest (see rpi_json.sql and
rpi_json.php) json serialisation and threading.
"""
import sys
import time, math, glob, random, threading, json

import demo
import pi3d
import pygame
import numpy as np
from PIL import Image, ImageDraw
import subprocess as sp
import threading
import time
import math
import random
import os


if sys.version_info[0] == 3:
  from urllib import request as urllib_request
  from urllib import parse as urllib_parse
else:
  import urllib
  urllib_request = urllib
  urllib_parse = urllib

W, H, P = 640, 360, 3 # video width, height, bytes per pixel (3 = RGB)

#command = ['/usr/local/bin/ffmpeg', ' -i /home/pi/Documents/code/pi3d_demos/films/low.mp4 -f image2pipe -pix_fmt rgb24 -vcodec rawvideo -']

# 640 x 360

flag = False # use to signal new texture

print('starting')

class VidPlayer(object):
  def __init__(self):
    self.mood_index = -1
    self.mid_climax = False
    self.mood = ['/home/pi/Documents/code/pi3d_demos/films/transition.mp4', '/home/pi/Documents/code/pi3d_demos/films/low.mp4', '/home/pi/Documents/code/pi3d_demos/films/high.mp4']
    self.set_cmd(0, 0)
    self.image = np.zeros((H, W, P), dtype='uint8')
    self.flag = False
    t = threading.Thread(target=self.pipe_thread)
    t.daemon = True
    t.start()

  def set_mood(self, mood_index, limit=90, start=0):
    if (mood_index != self.mood_index) and (not self.mid_climax):
      self.set_cmd(mood_index, limit, start)
      #self.command = [ 'ffmpeg', '-ss', str(start + (random.random() * limit)), '-i', self.mood[mood_index], '-f', 'image2pipe', '-pix_fmt', 'rgb24', '-vcodec', 'rawvideo', '-']
      #self.command_flag = True
      #self.mood_index = mood_index

  def set_cmd(self, mood_index, limit=90, start=0):
    self.command = [ 'ffmpeg', '-ss', str(start + (random.random() * limit)), '-i', self.mood[mood_index], '-f', 'image2pipe', '-pix_fmt', 'rgb24', '-vcodec', 'rawvideo', '-']
    self.command_flag = True
    self.mood_index = mood_index

  def ready(self):
    return(self.flag)

  def climax(self):
    if (not self.mid_climax):
      self.set_cmd(2, 0, 42.5)
      self.mid_climax = True
    
  def pipe_thread(self):
    #global flag, image, tex
    pipe = None
    while True:
      st_tm = time.time()
      #print('ready to open pipe')
      if (pipe is None) or (self.command_flag):
        if (pipe is not None):
          pipe.kill()
        pipe = sp.Popen(self.command, stdout=sp.PIPE, stderr=sp.PIPE, bufsize=-1)
        self.command_flag = False
      #print('pipe open')
      prev = self.image
      self.image =  np.fromstring(pipe.stdout.read(H * W * P), dtype='uint8')
      #print('got image')
      pipe.stdout.flush() # presumably nothing else has arrived since read()
      pipe.stderr.flush() # ffmpeg sends commentary to stderr
      if len(self.image) < H * W * P: # end of video, reload
        self.image = prev
        pipe.terminate()
        pipe = None
        if self.mid_climax:
          self.mid_climax = False
          self.set_cmd(0,0)
      else:
        self.image.shape = (H, W, P)
        self.flag = True
        self.tex = pi3d.Texture(self.image) #if this is here, we can avoid race conditions
      #print('we get here')
      step = time.time() - st_tm
      time.sleep(max((1/15) - step, 0.0)) # adding fps info to ffmpeg doesn't seem to have any effect


  def get_image(self):
    if self.flag:
      self.flag = False
      return(self.image)

  def get_tex(self):
    if self.flag:
      self.flag = False
      self.tex.update_ndarray(self.image)
      return(self.tex)

print ('def vidplayer')
vplayer =VidPlayer()
while vplayer.ready() is False:
  time.sleep(1.0)
print('got vidplayer')

arousal = 0
ejaculation=0
EXCITED_THRESH = 20
ORGASMIC_THRESH = 1000
NEAR = ORGASMIC_THRESH * 0.9
REPOSE = -500
PAUSE = 1

#pygame.init()
#display, camera, shader
DISPLAY = pi3d.Display.create(x=100, y=100, frames_per_second=20,use_pygame=True)
#
#DISPLAY = pi3d.Display.create(frames_per_second=20,use_pygame=True)
#a default camera is created automatically but we might need a 2nd 2D camera
#for displaying the instruments etc. Also, because the landscape is large
#we need to set the far plane to 10,000
CAMERA = pi3d.Camera(lens=(1.0, 10000.0, 55.0, 1.6))
CAMERA2D = pi3d.Camera(is_3d=False)

print("""===================================
== W increase power, S reduce power
== V view mode, C control mode
== B brakes
== mouse movement joystick
== Left button fire!
== X jumps to location of 1st enemy in list
================================""")

SHADER = pi3d.Shader("uv_bump") #for objects to look 3D
FLATSH = pi3d.Shader("uv_flat") #for 'unlit' objects like the background

flatwhite = pi3d.Texture("textures/white.png")
xoffset = 0#-13.799986457824705
yoffset = 0#-189.01106018066403
zoffset = 0#-22.439974822998053

GRAVITY = 9.8 #m/s**2
LD = 10 #lift/drag ratio
DAMPING = 0.95 #reduce roll and pitch rate each update_variables
BOOSTER = 1.5 #extra manoevreability boost to defy 1st Low of Thermodynamics.
#load bullet images
BULLET_TEX = [] #list to hold Texture refs
iFiles = glob.glob(sys.path[0] + "/textures/biplane/bullet??.png") 
iFiles.sort() # order is vital to animation!
for f in iFiles:
  BULLET_TEX.append(pi3d.Texture(f))
DAMAGE_FACTOR = 50 #dived by distance of shoot()
NR_TM = 1.0 #check much less frequently until something comes back
FA_TM = 5.0
NR_DIST = 250
FA_DIST = 1500
P_FACTOR = 0.001
I_FACTOR = 0.00001

#define Aeroplane class
class Aeroplane(object):
  def __init__(self, model, recalc_time, refid):
    self.refid = refid
    self.recalc_time = recalc_time #in theory use different values for enemy
    self.x, self.y, self. z = 0.0, 0.0, 0.0
    self.x_perr, self.y_perr, self.z_perr = 0.0, 0.0, 0.0
    self.x_ierr, self.y_ierr, self.z_ierr = 0.0, 0.0, 0.0
    self.d_err = 0.0
    self.v_speed, self.h_speed = 0.0, 0.0
    self.rollrate, self.pitchrate, self.yaw = 0.0, 0.0, 0.0
    self.direction, self.roll, self.pitch = 0.0, 0.0, 0.0
    self.max_roll, self.max_pitch = 65, 30 #limit rotations
    self.ailerons, self.elevator = 0.0, 0.0
    self.max_ailerons, self.max_elevator = 10.0, 10.0 #limit conrol surface movement
    self.VNE = 120 #max speed (Velocity Not to be Exceeded)
    self.mass = 300
    self.a_factor, self.e_factor = 10, 10
    self.roll_inrta, self.pitch_inrta = 100, 100
    self.max_power = 2000 #force units of thrust really
    self.lift_factor = 20.0 #randomly adjusted to give required performance!
    self.power_setting = 0.0
    self.throttle_step = 20
    self.last_time = time.time()
    self.last_pos_time = self.last_time
    self.del_time = None #difference in pi time for other aero c.f. main one
    self.rtime = 60
    self.nearest = None
    self.other_damage = 0.0 #done to nearest others since last json_load
    self.damage = 0.0 #done to this aeroplane by others
    #create the actual model
    self.model = pi3d.Model(file_string=model, camera=CAMERA)
    self.model.set_shader(SHADER)
    self.model.set_normal_shine(flatwhite, 16.0, flatwhite, 0.5)
    #roration by Les
    self.model.rotateToX(xoffset)
    self.model.rotateToY(yoffset)
    self.model.rotateToZ(zoffset)
    #create the bullets
    plane = pi3d.Plane(h=25, w=1)
    self.bullets = pi3d.MergeShape(camera=CAMERA)
    #the merge method does rotations 1st Z, 2nd X, 3rd Y for some reason
    #for multi axis rotations you need to figure it out by rotating a
    #sheet of paper in the air in front of you (angles counter clockwise)!
    self.bullets.merge([[plane, -2.0, 0.5, 8.0, 90,0,0, 1,1,1],
                        [plane, -2.0, 0.5, 8.0, 0,90,90, 1,1,1],
                        [plane, 2.0, 0.5, 8.0, 90,0,0, 1,1,1],
                        [plane, 2.0, 0.5, 8.0, 0,90,90, 1,1,1]])
    self.num_b = len(BULLET_TEX)
    self.seq_b = self.num_b
    self.bullets.set_draw_details(FLATSH, [BULLET_TEX[0]])

  def set_ailerons(self, dx):
    self.ailerons = dx
    if abs(self.ailerons) > self.max_ailerons:
      self.ailerons = math.copysign(self.max_ailerons, self.ailerons)

  def set_elevator(self, dy):
    self.elevator = dy
    if abs(self.elevator) > self.max_elevator:
      self.elevator = math.copysign(self.max_elevator, self.elevator)

  def set_power(self, incr):
    self.power_setting += incr * self.throttle_step
    if self.power_setting < 0:
      self.power_setting = 0
    elif self.power_setting > self.max_power:
      self.power_setting = self.max_power

  #Les adds this for z thing on joystick
  def stick_power(self, level): # level is -1 to + 1
    level = level /-2
    level = level + 0.5
    self.power_setting = self.max_power * level
    if self.power_setting < 0:
      self.power_setting = 0
    elif self.power_setting > self.max_power:
      self.power_setting = self.max_power

  
  def shoot(self, target):
    #only shoot if animation seq. ended
    if self.seq_b < self.num_b:
      return 0.0
    #animate bullets
    self.seq_b = 0
    #check for hit
    #components of direction vector
    diag_xz = math.cos(math.radians(self.pitch))
    drn_x = diag_xz * math.sin(math.radians(self.direction))
    drn_y = math.sin(math.radians(self.pitch))
    drn_z = diag_xz * math.cos(math.radians(self.direction))
    #this will already be a unit vector
    #vector from target to aeroplane
    a_x = target[0] - self.x
    a_y = target[1] - self.y
    a_z = target[2] - self.z
    #dot product
    dot_p = drn_x * a_x + drn_y * a_y + drn_z * a_z
    dx = a_x - dot_p * drn_x
    dy = a_y - dot_p * drn_y
    dz = a_z - dot_p * drn_z
    distance = math.sqrt(dx**2 + dy**2 + dz**2)
    print("distance={0:.2f}".format(distance))
    return DAMAGE_FACTOR / distance if distance > 0.0 else 2.0 * DAMAGE_FACTOR

  def home(self, target):
    #turn towards target location, mainly for AI control of enemy aircraft
    dir_t = math.degrees(math.atan2((target[0] - self.x), (target[2] - self.z)))
    #make sure the direction is alway a value between +/- 180 degrees
    #roll so bank is half direction, 
    self.roll = -((dir_t - self.direction + 180) % 360 - 180) / 2
    #find angle between self and target
    pch_t = math.degrees(math.atan2((target[1] - self.y),
            math.sqrt((target[2] - self.z)**2 + (target[0] - self.x)**2)))
    self.pitch = pch_t
    return True

  def update_variables(self):
    #time
    tm = time.time()
    dt = tm - self.last_time
    if dt < self.recalc_time: # don't need to do all this physics every loop
      return
    self.last_time = tm
    #force from ailerons and elevators to get rotational accelerations
    spsq = self.v_speed**2 + self.h_speed**2 #speed squared
    a_force = self.a_factor * self.ailerons * spsq #ailerons force (moment really)
    roll_acc = a_force / self.roll_inrta #good old Newton
    e_force = self.e_factor * self.elevator * spsq #elevator
    pitch_acc = e_force / self.pitch_inrta
    #velocities and positions
    if abs(self.roll) > self.max_roll: #make it easier to do flight control
      self.roll = math.copysign(self.max_roll, self.roll)
      self.rollrate = 0.0
    if abs(self.pitch) > self.max_pitch:
      self.pitch = math.copysign(self.max_pitch, self.pitch)
      self.pitchrate = 0.0
    self.roll += self.rollrate * dt #update roll position
    self.pitch += self.pitchrate * dt #update roll rate
    self.rollrate += roll_acc * dt
    self.rollrate *= DAMPING # to stop going out of contol while looking around!
    self.pitchrate += pitch_acc * dt
    self.pitchrate *= DAMPING
    #angle of attack
    aofa = math.atan2(self.v_speed, self.h_speed)
    aofa = math.radians(self.pitch) - aofa # approximation to sin difference
    lift = self.lift_factor * spsq * aofa
    drag = lift / LD 
    if spsq < 100: #stall!
      lift *= 0.9
      drag *= 1.3

    #print('speed', self.v_speed)
    #Les hack
    if (self.h_speed ==0):
      lift = 0
      v_force = self.mass * GRAVITY *-1
      v_acc = GRAVITY * -1 #v_force / self.mass
      self.y -= GRAVITY #bad hack
    #


    cos_pitch = math.cos(math.radians(self.pitch))
    sin_pitch = math.sin(math.radians(self.pitch))
    cos_roll = math.cos(math.radians(self.roll))
    sin_roll = math.sin(math.radians(self.roll))
    h_force = (self.power_setting - drag) * cos_pitch - lift * sin_pitch
    v_force = lift * cos_pitch * cos_roll - self.mass * GRAVITY
    h_acc = h_force / self.mass
    v_acc = v_force / self.mass
    self.h_speed += h_acc * dt
    if self.h_speed > self.VNE:
      self.h_speed = self.VNE
    elif self.h_speed < 0:
      self.h_speed = 0
    self.v_speed += v_acc * dt
    if abs(self.v_speed) > self.VNE:
      self.v_speed = math.copysign(self.VNE, self.v_speed)
    turn_force = -lift * sin_roll * 1.5
    radius = self.mass * spsq / turn_force if turn_force != 0.0 else 0.0
    self.yaw = math.sqrt(spsq) / radius if radius != 0.0 else 0.0

  def update_position(self, height, mapsize):
    #time
    tm = time.time()
    dt = tm - self.last_pos_time
    self.last_pos_time = tm

    self.x += (self.h_speed * math.sin(math.radians(self.direction)) * dt -
              self.x_perr * P_FACTOR - self.x_ierr * I_FACTOR)
    self.y += self.v_speed * dt - self.y_perr * P_FACTOR - self.y_ierr * I_FACTOR
    if self.y < (height + 3):
      self.y = height + 3
      self.v_speed = 0
      self.pitch = 2.5
      #self.roll = 0

    # les hack
    #print(self.y)
    if self.y > 2400:
      #print('peak')
      self.y=2400
    #  
    self.z += (self.h_speed * math.cos(math.radians(self.direction)) * dt -
              self.z_perr * P_FACTOR - self.z_ierr * I_FACTOR)

    self.direction += math.degrees(self.yaw) * dt - self.d_err * P_FACTOR
    #set values of model
    sin_d = math.sin(math.radians(self.direction))
    cos_d = math.cos(math.radians(self.direction))
    sin_r = math.sin(math.radians(self.roll))
    cos_r = math.cos(math.radians(self.roll))
    sin_p = math.sin(math.radians(self.pitch))
    cos_p = math.cos(math.radians(self.pitch))
    absroll = math.degrees(math.asin(sin_r * cos_d + cos_r * sin_p * sin_d))
    abspitch = math.degrees(math.asin(sin_r * sin_d - cos_r * sin_p * cos_d))
    #print ('postion', self.x, self.y, self.z)
    # Les offsets
    self.model.rotateToX((abspitch * 0.3)+ xoffset)
    self.model.rotateToY(self.direction + yoffset)
    self.model.rotateToZ((absroll * 0.5) + zoffset)

    # Les map wrap
    mapsize *= 0.7
    halfsize = (mapsize/2)
    xm = (self.x + halfsize) % mapsize - halfsize # wrap location to stay on map -500 to +500
    zm = (self.z + halfsize) % mapsize - halfsize

    #if ((xm != self.x) or (zm != self.z)):
    #  print(xm, zm)

    self.x = xm
    self.z = zm

    self.model.position(self.x, self.y, self.z)

    
    #set values for bullets
    if self.seq_b < self.num_b:
      self.bullets.position(self.x, self.y, self.z)
      self.bullets.rotateToX(abspitch)
      self.bullets.rotateToY(self.direction)
      self.bullets.rotateToZ(absroll)
    #set values for camera
    return (self.x - 10.0 * sin_d, self.y + 4, self.z - 10.0 * cos_d, self.direction)

  def draw(self):
    self.model.draw()
    #draw the bullet sequence if not finished
    if self.seq_b < self.num_b:
      self.bullets.buf[0].textures[0] = BULLET_TEX[self.seq_b]
      self.bullets.draw()
      self.seq_b += 1

#define Instruments class
class Instruments(object):
  def __init__(self):
    wd = DISPLAY.width
    ht = DISPLAY.height
    asi_tex = pi3d.Texture("textures/airspeed_indicator.png")
    alt_tex = pi3d.Texture("textures/altimeter.png")
    #rad_tex = pi3d.Texture("textures/radar.png")
    #dot_tex = pi3d.Texture("textures/radar_dot.png")
    ndl_tex = pi3d.Texture("textures/instrument_needle.png")
    self.asi = pi3d.ImageSprite(asi_tex, FLATSH, camera=CAMERA2D,
          w=128, h=128, x=-128, y=-ht/2+64, z=2)
    self.alt = pi3d.ImageSprite(alt_tex, FLATSH, camera=CAMERA2D,
          w=128, h=128, x=0, y=-ht/2+64, z=2)
    #self.rad = pi3d.ImageSprite(rad_tex, FLATSH, camera=CAMERA2D,
    #      w=128, h=128, x=128, y=-ht/2+64, z=2)
    #self.dot = pi3d.ImageSprite(dot_tex, FLATSH, camera=CAMERA2D,
    #      w=16, h=16, z=1)
    self.ndl1 = pi3d.ImageSprite(ndl_tex, FLATSH, camera=CAMERA2D,
          w=128, h=128, x=-128, y=-ht/2+64, z=1)
    self.ndl2 = pi3d.ImageSprite(ndl_tex, FLATSH, camera=CAMERA2D,
          w=128, h=128, x=0, y=-ht/2+64, z=1)
    #self.ndl3 = pi3d.ImageSprite(ndl_tex, FLATSH, camera=CAMERA2D,
    #      w=128, h=128, x=128, y=-ht/2+64, z=1)
    #self.dot_list = []
    
    #tex = pi3d.Texture(image) not in this thread
    vidw = W * 0.7
    vidh = H *0.7
    self.vid = pi3d.ImageSprite(vplayer.get_tex(), FLATSH, camera=CAMERA2D,
          w=vidw, h=vidh, x=((wd/2)-(vidw/2)), y=(-ht/2)+(vidh/2), z=2)
    self.update_time = 0.0
    
  def draw(self):
    global flag
    self.asi.draw()
    self.alt.draw()
    #self.rad.draw()
    #for i in self.dot_list:
    #  self.dot.position(i[1] + 128, i[2] + self.rad.y(), 1)
    #  self.dot.draw()
    self.ndl1.draw()
    self.ndl2.draw()
    #self.ndl3.draw()
    # put it in the video reading thread instead or there will be trouble
    #tex = pi3d.Texture(image) # can pass numpy array or PIL.Image rather than path as string
    self.vid.draw()

    
  def update(self, ae): #, others
    global flag
    self.ndl1.rotateToZ(-360*ae.h_speed/140)
    #print(-360*ae.h_speed/140)
    self.ndl2.rotateToZ(-360*ae.y/3000)
    #self.ndl3.rotateToZ(-ae.direction)
    #self.dot_list = []
    #for i in others:
    #  if i == "start":
    #    continue
    #  o = others[i]
    #  dx = (o.x - ae.x) / 50
    #  dy = (o.z - ae.z) / 50
    #  d = math.hypot(dx, dy)
    #  if d > 40:
    #    dx *= 40 / d
    #    dy *= 40 / d
    #  self.dot_list.append([o.refid, dx, dy])
    #update rate too slow
    """
    if flag:
      tex.update_ndarray(image)
      flag = False
      self.vid.set_textures([tex])
    """
    self.update_time = ae.last_pos_time

def json_load(ae, others):
  """httprequest other players. Sends own data and gets back array of all
  other players within sight. This function runs in a background thread
  """
  #TODO pass nearest, nearest.hp and own hp merge in some way
  tm_now = time.time()
  jstring = json.dumps([ae.refid, ae.last_time, ae.x, ae.y, ae.z,
      ae.h_speed, ae.v_speed, ae.pitch, ae.direction, ae.roll,
      ae.pitchrate, ae.yaw, ae.rollrate, ae.power_setting, ae.damage], separators=(',',':'))
  if ae.nearest:
    n_id = ae.nearest.refid
    n_damage = ae.nearest.other_damage
    ae.nearest.other_damage = 0.0
  else:
    n_id = ""
    n_damage = 0.0
  params = urllib_parse.urlencode({"id":ae.refid, "tm":tm_now, "x":ae.x, "z":ae.z,
          "json":jstring, "nearest":n_id, "damage":n_damage})
  others["start"] = tm_now #used for polling freqency
  urlstring = "http://www.eldwick.org.uk/sharecalc/rpi_json.php?{0}".format(params)
  try:
    r = urllib_request.urlopen(urlstring)
    if r.getcode() == 200: #good response
      jstring = r.read().decode("utf-8")
      if len(jstring) > 50: #error messages are shorter than this
        olist = json.loads(jstring)
        #smooth time offset value
        ae.del_time = ae.del_time * 0.9 + olist[0] * 0.1 if ae.del_time else olist[0]
        #own damage is cumulative and not reset on server until dead!
        ae.damage = olist[1]
        #if ae.damage > 2.0 * DAMAGE_FACTOR: #explode return to GO etc
        #print(ae.damage)
        olist = olist[2:]
        """
        synchronisation system: sends time.time() which is used to calculate
        an offset on the server and which is inserted as the second term 
        in the json string. When the list of other players comes back from
        the server it is preceded by the same offset time inserted in this json.
        This is used to adjust the last_time for all
        the other avatars.
        """
        nearest = None
        ae.rtime = 60
        for o in olist:
          if not(o[0] in others):
            others[o[0]] = Aeroplane("models/biplane.obj", 0.1, o[0])#Aeroplane("models/Drome/drone.obj", 0.1, o[0])#Aeroplane("models/biplane.obj", 0.1, o[0])
          oa = others[o[0]] #oa is other aeroplane, ae is this one!
          oa.refif = o[0]
          #exponential smooth time offset values
          oa.del_time = oa.del_time * 0.9 + o[1] * 0.1 if oa.del_time else o[1]
          oa.last_time = o[2] + oa.del_time - ae.del_time # o[1] inserted by server code
          dt = tm_now - oa.last_time
          if oa.x == 0.0:
            oa.x, oa.y, oa.z = o[3], o[4], o[5]
          nx = o[3] + o[6] * math.sin(math.radians(o[9])) * dt
          ny = o[4] + o[7] * dt
          nz = o[5] + o[6] * math.cos(math.radians(o[9])) * dt
          distance = math.hypot(nx - ae.x, nz - ae.z)
          if not nearest or distance < nearest:
            nearest = distance
            ae.nearest = oa
          oa.x_perr, oa.y_perr, oa.z_perr = oa.x - nx, oa.y - ny, oa.z - nz
          oa.x_ierr += oa.x_perr
          oa.y_ierr += oa.y_perr
          oa.z_ierr += oa.z_perr
          oa.d_err = ((oa.direction - (o[9] + o[12] * dt) + 180) % 360 - 180) / 2
          oa.h_speed = o[6]
          oa.v_speed = o[7]
          oa.pitch = o[8]
          oa.roll = o[10]
          oa.pitchrate = o[11]
          oa.yaw = o[12]
          oa.rollrate = o[13]
          oa.power_setting = o[14]
          oa.damage = o[15]

        if nearest:
          ae.rtime = NR_TM + (max(min(nearest, FA_DIST), NR_DIST) - NR_DIST) / \
                  (FA_DIST - NR_DIST) * (FA_TM - NR_TM)
        #TODO tidy up inactive others; flag not to draw, delete if inactive for long enough
        return True
      else:
        print(jstring)
        return False
    else:
      print(r.getcode())
      return False
  except Exception as e:
    print("exception:", e)

#MAC address
try:
  refid = (open("/sys/class/net/eth0/address").read()).strip()
except:
  try:
    refid = (open("/sys/class/net/wlan0/address").read()).strip()
  except:
    refid = "00:00:00:00:00:00"
#create the instances of Aeroplane - this is the one that draws
    #switched to cube for testing
a = Aeroplane("models/Drone/drone.obj", 0.02, refid)#Aeroplane("models/biplane.obj", 0.02, refid)
a.z, a.direction = 900, 180
#create instance of instruments
inst = Instruments()
# won't be on network and don't need this
#others = {"start": 0.0} #contains a dictionary of other players keyed by refid
#thr = threading.Thread(target=json_load, args=(a, others))
#thr.daemon = True #allows the program to exit even if a Thread is still running
#thr.start()
# Load textures for the environment cube
ectex = pi3d.loadECfiles("textures/ecubes", "sbox")
myecube = pi3d.EnvironmentCube(size=7000.0, maptype="FACES", camera=CAMERA)
myecube.set_draw_details(FLATSH, ectex)
myecube.set_fog((0.5,0.5,0.5,1.0), 3500) #was 4000
# Create elevation map
mapwidth = 10000.0
mapdepth = 10000.0
mapheight = 1000.0
mountimg1 = pi3d.Texture("textures/mountains3_512.jpg")
bumpimg = pi3d.Texture("textures/grasstile_n.jpg")
reflimg = pi3d.Texture("textures/stars.jpg")
mymap = pi3d.ElevationMap("textures/mountainsHgt.jpg", name="map",
                     width=mapwidth, depth=mapdepth, height=mapheight,
                     divx=64, divy=64, camera=CAMERA)
mymap.set_draw_details(SHADER, [mountimg1, bumpimg, reflimg], 1024.0, 0.0)
mymap.set_fog((0.5, 0.5, 0.5, 1.0), 4000)
# Les adds clouds
cloudno = 20
cloud_depth = 350.0

cloudTex = []
cloudTex.append(pi3d.Texture("textures/cloud2.png",True))
cloudTex.append(pi3d.Texture("textures/cloud3.png",True))
cloudTex.append(pi3d.Texture("textures/cloud4.png",True))
cloudTex.append(pi3d.Texture("textures/cloud5.png",True))
cloudTex.append(pi3d.Texture("textures/cloud6.png",True))

"""
# Setup cloud positions and cloud image refs
cz = 0.0
clouds = [] # an array for the clouds
inc = 4100/cloudno
for b in range (0, cloudno):
  size = 0.5 + random.random()/2.0
  cloud = pi3d.Sprite(w=inc, h=1000,
          x=4200, y=10.0, z=inc*b)
  cloud.set_draw_details(SHADER, [cloudTex[int(random.random() * 4.99999)]], 0.0, 0.0)
  cloud.rotateIncY(90)
  clouds.append(cloud)
for b in range (0, cloudno):
  size = 0.5 + random.random()/2.0
  cloud = pi3d.Sprite(w=inc, h=1000,
          x=inc*b, y=100.0, z=4200)
  cloud.set_draw_details(SHADER, [cloudTex[int(random.random() * 4.99999)]], 0.0, 0.0)
  cloud.rotateIncY(90)
  clouds.append(cloud)
"""
# init events keyboard/mouse
"""
inputs = pi3d.InputEvents()
inputs.get_mouse_movement()
"""
#Les adds some joystick support
#"""
pygame.init()
pygame.joystick.init()
joystick = pygame.joystick.Joystick(0)
joystick.init()
print(joystick.get_name())
#"""

#audio
pygame.mixer.init()
pygame.mixer.set_num_channels(1)
sfx = pygame.mixer.Channel(0)

sfxFiles = glob.glob("sfx/moan*.aiff")
random.shuffle(sfxFiles)
nSFX = len(sfxFiles)
iSFX = 0
#load the first moan
moan=pygame.mixer.Sound(sfxFiles[iSFX % nSFX])
iSFX += 1

orgasmSFX = pygame.mixer.Sound('sfx/orgasm.wav')

last_moan = 0


def touch ():
    print ('touch')
    if not os.path.exists('/tmp/sexbot1'):
        open('/tmp/sexbot1', 'a').close() 
    return



touch()
count = 0
should_touch = 20 * 60 # once per minute

a.stick_power(-0.25)
#a.set_power(1)

CAMERA.position((0.0, 0.0, -10.0))
cam_rot, cam_pitch = 0, 0
cam_toggle = True #control mode
#DISPLAY.resize()
while DISPLAY.loop_running(): #and not inputs.key_state("KEY_ESC"):
  """ mouse/keyboard input
  #inputs.do_input_events()
  mx, my, mv, mh, md = inputs.get_mouse_movement()
  # joystick
  """
  pygame.event.pump()
  mx = joystick.get_axis(0)
  my = joystick.get_axis(1)
  mz = joystick.get_axis(2)

  ejaculation = 0

  # Do the arousal bits
  if((mx == 0) and (my == 0)):
    #nothing happening to the stick
    if (arousal < -10):
      if (arousal < (REPOSE+12)):
        a.shoot([0, 0, 0])
      arousal += 1
    else:
      vplayer.set_mood(0,1)
      arousal -= 1
      if (arousal < 0) :
        arousal = 0
  else :
    #touching the stick
    arousal += 1
    #print(arousal)

    if(arousal >=ORGASMIC_THRESH):
      sfx.queue(orgasmSFX)
      ejaculation = 1
      arousal = REPOSE
      # change video to orgasm
      vplayer.climax()
      a.shoot([0, 0, 0])
    elif(arousal >= EXCITED_THRESH):
      #print ('hott!')
      
      pause = (ORGASMIC_THRESH - arousal)/280 + PAUSE
      if pause < 1.5:
        vplayer.set_mood(2,5)
      else:
        vplayer.set_mood(1)
      #print (pause)
      if (not sfx.get_busy()) and (time.time() - last_moan > pause):
        print (arousal, 'moan', sfxFiles[iSFX])
        sfx.play(moan)
        #get ready for the next one
        moan=pygame.mixer.Sound(sfxFiles[iSFX])
        iSFX += 1
        iSFX = iSFX % nSFX
        last_moan = time.time()

  #mx, my, mz = inputs.get_joystick3d()
  """
  #a.stick_power(mz)
  
  #print(mx, my, mz)
  # mouse input
  if cam_toggle:
    a.set_ailerons(-mx * 0.001)
    a.set_elevator(my * 0.001)
  else:
    cam_rot -= mx * 0.1
    cam_pitch -= my * 0.1
  #"""
  #""" joystick input
  #mx, my = inputs.get_joystickR()
  if cam_toggle:
    a.set_ailerons(-mx * 0.01)#0.06)
    a.set_elevator(my * 0.01)#0.02)
  else:
    cam_rot -= mx * 2.0
    cam_pitch -= my * 2.0
  """
  
  if inputs.key_state("KEY_W") or inputs.get_hat()[1] == -1: #increase throttle
    a.set_power(1)
  if inputs.key_state("KEY_S") or inputs.get_hat()[1] == 1: #throttle back
    a.set_power(-1)
  if inputs.key_state("KEY_X"): #jump to first enemy!
    for i in others:
      if i != "start":
        b = others[i]
        a.x, a.y, a.z = b.x, b.y + 5, b.z
        break
  if inputs.key_state("KEY_B") or inputs.key_state("BTN_BASE2"): #brakes
    a.h_speed *= 0.99
  if inputs.key_state("KEY_V") or inputs.key_state("BTN_TOP2"): #view mode
    cam_toggle = False
    a.set_ailerons(0)
    a.set_elevator(0)
  if inputs.key_state("KEY_C") or inputs.key_state("BTN_BASE"): #control mode
    cam_toggle = True
    cam_rot, cam_pitch = 0, 0
  if inputs.key_state("BTN_LEFT") or inputs.key_state("BTN_PINKIE"): #shoot
    #target is always nearest others set during last json_load()
    #tx, ty, tz = 0., 0.0, 0.0
    if a.nearest:
      tx, ty, tz = a.nearest.x, a.nearest.y, a.nearest.z
      a.nearest.other_damage += a.shoot([tx, ty, tz])

  if inputs.key_state("KEY_A"):
    xoffset += 0.23
  elif inputs.key_state("KEY_S"):
    xoffset -= 0.23
  elif inputs.key_state("KEY_D"):
    yoffset += 0.41
  elif inputs.key_state("KEY_F"):
    yoffset -= 0.41
  elif inputs.key_state("KEY_G"):
    zoffset += 0.12
  elif inputs.key_state("KEY_H"):
    zoffset -= 0.12
  elif inputs.key_state("KEY_J"):
    print(xoffset, yoffset, zoffset, '\n')
  """

  a.update_variables()
  loc = a.update_position(mymap.calcHeight(a.x, a.z), mapwidth)
  CAMERA.reset()
  CAMERA.rotate(-20 + cam_pitch, -loc[3] + cam_rot, 0) #unreal view
  #CAMERA.rotate(-20 + cam_pitch, -loc[3] + cam_rot, -a.roll) #air-sick view
  CAMERA.position((loc[0], loc[1], loc[2]))

  #moved draw

  mymap.draw()

  limit = mapwidth / 2
  
  if abs(loc[0]) > limit:
    mymap.position(math.copysign(limit,loc[0]), 0.0, 0.0)
    mymap.draw()
  if abs(loc[2]) > limit:
    mymap.position(0.0, 0.0, math.copysign(limit,loc[2]))
    mymap.draw()
  
    #if abs(loc[1]) > 300:
    #  mymap.position(math.copysign(1000,loc[0]), 0.0, math.copysign(1000,loc[2]))
    #  mymap.draw()
  mymap.position(0.0, 0.0, 0.0)

  #mymap.draw()
  myecube.position(loc[0], loc[1], loc[2])
  myecube.draw()

  """
  for cloud in clouds:
    cloud.positionY(a.y)
    #print (cloud.y, a.y)
    cloud.draw()
  """

  #if flag:
  #  tex.update_ndarray(image)
  #  flag = False
  #  inst.vid.set_textures([tex])
  if vplayer.ready():
    vtex = vplayer.get_tex()
    inst.vid.set_textures([vtex])
  
  inst.draw()
  a.draw()

  # no others
  #for i in others:
  #  if i == "start":
  #    continue
  #  b = others[i]
  #  b.update_variables()
  #  b.update_position(mymap.calcHeight(b.x, b.z))
  #  b.draw()
  #do httprequest if thread not already started and enough time has elapsed
  #if not (thr.isAlive()) and (a.last_pos_time > (others["start"] + a.rtime)):
  #  thr = threading.Thread(target=json_load, args=(a, others))
  #  thr.daemon = True #allows the program to exit even if a Thread is still running
  #  thr.start()
    
  if a.last_pos_time > (inst.update_time + NR_TM):
    inst.update(a)

  #was draw
  count = count + 1
  count %= should_touch
  if (count == 0):
    touch()


#inputs.release()
DISPLAY.destroy()
