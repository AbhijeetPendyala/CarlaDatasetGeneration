# Append path of carla egg file into sys

import sys
import os
import settings
sys.path.append(settings.CARLA_EGG_PATH)

# Imports

import carla
import random
import time, math
import numpy as np
from PIL import Image
import pandas as pd
import re
from spawn_npc import NPCClass
from client_bounding_boxes import ClientSideBoundingBoxes
from set_synchronous_mode import CarlaSyncMode
from bb_filter import apply_filters_to_3d_bb
from WeatherSelector import WeatherSelector

##Main class

class CarlaWorld:

    def __init__(self):
        # Carla initialization
        client = carla.Client('localhost', 2000)
        self.client=client
        client.set_timeout(20.0)
        self.world = client.get_world()
        print('Successfully connected to CARLA')
        self.blueprint_library = self.world.get_blueprint_library()

        # Sensors stuff
        self.camera_x_location = 1.0
        self.camera_y_location = 0.0
        self.camera_z_location = 2.0
        self.sensors_list = []

        # Weather stuff
        self.weather_options = WeatherSelector().get_weather_options()  # List with weather options

        # Recording stuff
        self.total_recorded_frames = 0
        self.first_time_simulating = True

    def set_weather(self, weather_option):
        # Dynamic Weather
        weather = carla.WeatherParameters(*weather_option)
        self.world.set_weather(weather)

    def remove_npcs(self):
        print('Destroying actors...')
        self.NPC.remove_npcs()
        print('Done destroying actors.')

    def spawn_npcs(self, number_of_vehicles, number_of_walkers):
        self.NPC = NPCClass()
        self.vehicles_list, _ = self.NPC.create_npcs(number_of_vehicles, number_of_walkers)

    def put_rgb_sensor(self, vehicle, sensor_width=640, sensor_height=480, fov=110):

        bp = self.blueprint_library.find('sensor.camera.rgb')
        bp.set_attribute('image_size_x', f'{sensor_width}')
        bp.set_attribute('image_size_y', f'{sensor_height}')
        bp.set_attribute('fov', f'{fov}')

        # Adjust sensor relative position to the vehicle
        spawn_point = carla.Transform(carla.Location(x=self.camera_x_location, z=self.camera_z_location))
        self.rgb_camera = self.world.spawn_actor(bp, spawn_point, attach_to=vehicle)
        self.rgb_camera.blur_amount = 0.0
        self.rgb_camera.motion_blur_intensity = 0
        self.rgb_camera.motion_max_distortion = 0

        # Camera calibration
        calibration = np.identity(3)
        calibration[0, 2] = sensor_width / 2.0
        calibration[1, 2] = sensor_height / 2.0
        calibration[0, 0] = calibration[1, 1] = sensor_width / (2.0 * np.tan(fov * np.pi / 360.0))
        self.rgb_camera.calibration = calibration  # Parameter K of the camera
        self.sensors_list.append(self.rgb_camera)
        return self.rgb_camera

    def put_depth_sensor(self, vehicle, sensor_width=640, sensor_height=480, fov=110):

        bp = self.blueprint_library.find('sensor.camera.depth')
        bp.set_attribute('image_size_x', f'{sensor_width}')
        bp.set_attribute('image_size_y', f'{sensor_height}')
        bp.set_attribute('fov', f'{fov}')

        # Adjust sensor relative position to the vehicle
        spawn_point = carla.Transform(carla.Location(x=self.camera_x_location, z=self.camera_z_location))
        self.depth_camera = self.world.spawn_actor(bp, spawn_point, attach_to=vehicle)
        self.sensors_list.append(self.depth_camera)
        return self.depth_camera

    def process_depth_data(self, data, sensor_width, sensor_height):
        """
        normalized = (R + G * 256 + B * 256 * 256) / (256 * 256 * 256 - 1)
        in_meters = 1000 * normalized
        """
        data = np.array(data.raw_data)
        data = data.reshape((sensor_height, sensor_width, 4))
        data = data.astype(np.float32)
        # Apply (R + G * 256 + B * 256 * 256) / (256 * 256 * 256 - 1).
        normalized_depth = np.dot(data[:, :, :3], [65536.0, 256.0, 1.0])
        normalized_depth /= 16777215.0  # (256.0 * 256.0 * 256.0 - 1.0)
        depth_meters = normalized_depth * 1000
        return depth_meters

    def get_bb_data(self):

        vehicles_on_world = self.world.get_actors().filter('vehicle.*')
        walkers_on_world = self.world.get_actors().filter('walker.*')
        bounding_boxes_vehicles,df_1 = ClientSideBoundingBoxes.get_bounding_boxes(vehicles_on_world, self.rgb_camera)
        bounding_boxes_walkers,df_2 = ClientSideBoundingBoxes.get_bounding_boxes(walkers_on_world, self.rgb_camera)
        df_3 =[df_1, df_2]

        return [bounding_boxes_vehicles, bounding_boxes_walkers], df_3

    def process_rgb_img(self, img, sensor_width, sensor_height):
        img = np.array(img.raw_data)
        img = img.reshape((sensor_height, sensor_width, 4))
        img = img[:, :, :3]
        bb, df_3 = self.get_bb_data()
        return img, bb, df_3

    def remove_sensors(self):
        for sensor in self.sensors_list:
            sensor.destroy()
        self.sensors_list = []

    def begin_data_acquisition(self, sensor_width, sensor_height, fov, frames_to_record_one_ego=1, timestamps=[], egos_to_run=10):
        # Changes the ego vehicle to be put the sensor
        current_ego_recorded_frames = 0
        # These vehicles are not considered because the cameras get occluded without changing their absolute position
        ego_vehicle = random.choice([x for x in self.world.get_actors().filter("vehicle.*") if x.type_id not in
                                     ['vehicle.audi.tt', 'vehicle.carlamotors.carlacola', 'vehicle.volkswagen.t2']])
        self.put_rgb_sensor(ego_vehicle, sensor_width, sensor_height, fov)
        self.put_depth_sensor(ego_vehicle, sensor_width, sensor_height, fov)

        # Begin applying the sync mode
        with CarlaSyncMode(self.world, self.rgb_camera, self.depth_camera, fps=30) as sync_mode:
            # Skip initial frames where the car is being put on the ambient
            if self.first_time_simulating:
                for _ in range(30):
                    sync_mode.tick_no_data()

            while True:
                if current_ego_recorded_frames == frames_to_record_one_ego:
                    print('\n')
                    self.remove_sensors()
                    return timestamps
                # Advance the simulation and wait for the data
                # Skip every nth frame for data recording, so that one frame is not that similar to another
                wait_frame_ticks = 0
                while wait_frame_ticks < 5:
                    sync_mode.tick_no_data()
                    wait_frame_ticks += 1

                _, rgb_data, depth_data = sync_mode.tick(timeout=2.0)

                # Processing raw data
                vehicles_on_world = self.world.get_actors().filter('vehicle.*')
                walkers_on_world = self.world.get_actors().filter('walker.*')

                rgb_array, bounding_box, df_3 = self.process_rgb_img(rgb_data, sensor_width, sensor_height)

                depth_array = self.process_depth_data(depth_data, sensor_width, sensor_height)
                ego_speed = ego_vehicle.get_velocity()
                ego_speed = np.array([ego_speed.x, ego_speed.y, ego_speed.z])
                bounding_box, valid_df = apply_filters_to_3d_bb(bounding_box, depth_array, sensor_width,sensor_height,df_3)
                timestamp = round(time.time() * 1000.0)
                df_5_1= valid_df.drop(valid_df.columns[valid_df.columns.str.contains('unnamed',case = False)],axis = 1)
                df_5=df_5_1.copy()
                df_5.reset_index(inplace=True)
                total_length= len(df_5)
                COLUMN_NAMES = ['Type', 'BBox', 'Dimensions', 'Rotation_Y_(Red_Theta)', 'Alpha_(Blue_Theta)', 'Center_(ground_projection)']
                df = pd.DataFrame(columns=COLUMN_NAMES, dtype=object)

                if total_length:
                    for i in range(total_length):
                        temp_extent_1=str(df_5.vehiclesandwalkers[i].bounding_box.extent)
                        temp_extent_2=re.findall("[-+]?[.]?[\d]+(?:,\d\d\d)*[\.]?\d*(?:[eE][-+]?\d+)?", temp_extent_1)
                        temp_extent_3=list(np.float_(temp_extent_2))
                        temp_extent=temp_extent_3[1:]
                        temp_id= df_5.vehiclesandwalkers[i].id
                        temp_loc_1= str(df_5.vehiclesandwalkers[i].get_location())
                        temp_loc= re.findall("[-+]?[.]?[\d]+(?:,\d\d\d)*[\.]?\d*(?:[eE][-+]?\d+)?", temp_loc_1)
                        temp_param1=df_5.vehiclesandwalkers[i].type_id
                        temp_param2= temp_param1.split(".")
                        locyaw= df_5.vehiclesandwalkers[i].get_transform().rotation.yaw
                        relative_roation_y = (locyaw- ego_vehicle.get_transform().rotation.yaw)

                        if temp_param2[0]=='vehicle':
                            type='car'
                        else:
                            type='pedestrian'
                        temp_param = {'Type': type, 'BBox': df_5.twodbboxes[i], 'Dimensions': [i * 2 for i in temp_extent],'Rotation_Y_(Red_Theta)': relative_roation_y,'Alpha_(Blue_Theta)': locyaw, 'Center_(ground_projection)': temp_loc}
                        df = df.append(temp_param, ignore_index=True)

                # Create a directory to save dataset and check if it doesn't exists apriori
                if not os.path.exists('Data'):
                    os.mkdir('Data')
                # Save parameters
                df.to_csv('Data/' + str(timestamp) + '.txt', index= False)
                # Save images
                img = Image.fromarray(rgb_array, 'RGB')
                img.save('Data/'+"{0}_img".format(str(timestamp)), "png")